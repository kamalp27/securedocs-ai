"""Grounded Generative Q&A Service enforcing access-controlled retrieval and verified citations."""

import logging
from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.user import User
from app.rag.generation.base import BaseGeneratorProvider, GenerationResult
from app.rag.generation.citation_validator import CitationValidator
from app.rag.generation import get_generator_provider
from app.schemas.qa import Citation, QARequest, QAResponse, RetrievedChunkDiagnostic
from app.schemas.search import SearchResultItem
from app.services.retrieval_service import RetrievalService

logger = logging.getLogger("securedocs.qa.service")


class QAService:
    """
    Orchestrates grounded question-answering over authorized documents.
    Enforces strict access control via pre-retrieval authorization and validates
    all generated citations against verified retrieved chunks.
    """

    def __init__(
        self,
        retrieval_service: Optional[RetrievalService] = None,
        citation_validator: Optional[CitationValidator] = None,
        default_provider: Optional[BaseGeneratorProvider] = None,
    ):
        self._retrieval_service = retrieval_service
        self._citation_validator = citation_validator
        self._default_provider = default_provider

    @property
    def retrieval_service(self) -> RetrievalService:
        return self._retrieval_service or RetrievalService()

    @property
    def citation_validator(self) -> CitationValidator:
        return self._citation_validator or CitationValidator(require_snippet_containment=True)

    @property
    def default_provider(self) -> BaseGeneratorProvider:
        return self._default_provider or get_generator_provider()

    def get_provider(self, provider_name: Optional[str] = None) -> BaseGeneratorProvider:
        """Resolve the generator provider based on request or default fallback."""
        if provider_name:
            return get_generator_provider(provider_name)
        return self.default_provider

    def answer_question(
        self,
        db: Session,
        current_user: User,
        request: QARequest,
        ip_address: Optional[str] = None,
    ) -> QAResponse:
        """
        Execute end-to-end grounded question answering:
        1. Access-controlled semantic retrieval restricted strictly to user's authorized documents.
        2. If 0 chunks retrieved, return safe insufficient evidence response.
        3. If chunks retrieved, generate grounded answer using configured provider.
        4. Validate all candidate citations against actual retrieved chunks and snippets.
        5. Build safe diagnostics and return response.
        """
        clean_question = request.question.strip()

        # Step 1: Pre-retrieval authorized search
        # Uses the existing, battle-tested retrieval pipeline
        retrieved_chunks: List[SearchResultItem] = self.retrieval_service.search(
            db=db,
            current_user=current_user,
            query=clean_question,
            top_k=request.top_k,
            similarity_threshold=request.similarity_threshold,
        )

        provider = self.get_provider(request.provider)

        # Step 2: Insufficient evidence check if no chunks match or permitted
        if not retrieved_chunks:
            logger.info(
                "Zero authorized chunks found for user %s on question: %r",
                current_user.id,
                clean_question[:50],
            )
            # Log audit event for transparency
            self._log_qa_audit(
                db=db,
                user_id=current_user.id,
                query_text=clean_question,
                ip_address=ip_address,
                status_code=200,
            )

            return QAResponse(
                question=clean_question,
                answer="Insufficient evidence: I could not find sufficient evidence in your authorized documents to answer this question.",
                citations=[],
                insufficient_evidence=True,
                provider=provider.name,
                retrieved_chunk_count=0,
                retrieved_chunks=[],
            )

        # Step 3: Generate grounded answer via selected provider
        generation_result: GenerationResult = provider.generate(
            question=clean_question,
            retrieved_chunks=retrieved_chunks,
        )

        # Step 4: Validate proposed citations
        validated_citations: List[Citation] = []
        if generation_result.citations:
            validated_citations, rejected_count = self.citation_validator.validate_citations(
                raw_citations=generation_result.citations,
                retrieved_chunks=retrieved_chunks,
            )
            if rejected_count > 0:
                logger.warning(
                    "Filtered out %d ungrounded or invalid citations for question %r",
                    rejected_count,
                    clean_question[:50],
                )

        # If provider didn't declare insufficient evidence but yielded 0 valid citations
        # for a non-empty question, enforce insufficient evidence rather than ungrounded claims
        insufficient_evidence = generation_result.insufficient_evidence
        if not validated_citations and not insufficient_evidence:
            logger.info("Zero citations validated for question %r; marking insufficient evidence.", clean_question[:50])
            insufficient_evidence = True

        # Step 5: Safe diagnostic metadata
        diagnostics = [
            RetrievedChunkDiagnostic(
                chunk_id=c.chunk_id,
                document_id=c.document_id,
                original_filename=c.original_filename,
                similarity_score=c.similarity_score,
                page_number=c.page_number,
                section=c.section,
            )
            for c in retrieved_chunks
        ]

        # Log audit entry
        self._log_qa_audit(
            db=db,
            user_id=current_user.id,
            query_text=clean_question,
            ip_address=ip_address,
            status_code=200,
        )

        return QAResponse(
            question=clean_question,
            answer=generation_result.answer,
            citations=validated_citations,
            insufficient_evidence=insufficient_evidence,
            provider=generation_result.provider,
            retrieved_chunk_count=len(retrieved_chunks),
            retrieved_chunks=diagnostics,
        )

    @staticmethod
    def _log_qa_audit(
        db: Session,
        user_id: Optional[object],
        query_text: str,
        ip_address: Optional[str] = None,
        status_code: int = 200,
    ) -> None:
        """Record an audit trail log for Q&A queries."""
        try:
            audit = AuditLog(
                user_id=user_id,
                action="qa_query",
                query_text=query_text[:500],
                ip_address=ip_address,
                status_code=status_code,
            )
            db.add(audit)
            db.commit()
        except Exception as e:
            logger.error("Failed to commit Q&A audit log: %s", e)
            db.rollback()
