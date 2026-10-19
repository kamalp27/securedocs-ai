"""Citation validation and verification layer for grounded Q&A."""

import logging
import re
import uuid
from typing import Dict, List, Optional, Tuple

from app.rag.generation.base import RawCitation
from app.schemas.qa import Citation
from app.schemas.search import SearchResultItem

logger = logging.getLogger("securedocs.qa.citation_validator")


def normalize_snippet(text: str) -> str:
    """Normalize whitespace and lowercase for resilient fuzzy substring checking."""
    return re.sub(r"\s+", " ", text).strip().lower()


class CitationValidator:
    """
    Validates generator-proposed citations against the ground-truth set of
    retrieved chunks. Prevents hallucinations and falsified document references.
    """

    def __init__(self, require_snippet_containment: bool = True):
        self.require_snippet_containment = require_snippet_containment

    def validate_citations(
        self,
        raw_citations: List[RawCitation],
        retrieved_chunks: List[SearchResultItem],
    ) -> Tuple[List[Citation], int]:
        """
        Validate and enrich a list of candidate citations against retrieved chunks.

        Rules:
        1. chunk_id must exist in retrieved_chunks. Unknown/hallucinated chunk IDs are rejected.
        2. If quoted_snippet is present and require_snippet_containment is True,
           the snippet must appear within chunk.content (normalized). Snippets that fail
           containment check are rejected (citation dropped).
        3. Metadata (document_id, original_filename, page_number, section) is hydrated
           exclusively from the verified SearchResultItem, never trusted from generator.
        4. Deduplicates citations so each verified chunk is cited at most once per response.

        :return: (list_of_validated_citations, rejected_citation_count)
        """
        if not raw_citations or not retrieved_chunks:
            return [], len(raw_citations) if raw_citations else 0

        # Build lookup table of retrieved chunks by UUID
        chunk_map: Dict[uuid.UUID, SearchResultItem] = {
            chunk.chunk_id: chunk for chunk in retrieved_chunks
        }

        validated: List[Citation] = []
        seen_chunk_ids = set()
        rejected_count = 0

        for candidate in raw_citations:
            target_chunk = chunk_map.get(candidate.chunk_id)

            # Rule 1: Chunk ID existence check
            if not target_chunk:
                logger.warning(
                    "Rejected hallucinated citation with unknown chunk_id: %s",
                    candidate.chunk_id,
                )
                rejected_count += 1
                continue

            # Deduplication check
            if candidate.chunk_id in seen_chunk_ids:
                continue

            # Rule 2: Quoted snippet containment verification
            verified_snippet: Optional[str] = None
            if candidate.quoted_snippet and candidate.quoted_snippet.strip():
                clean_snippet = candidate.quoted_snippet.strip()
                norm_snippet = normalize_snippet(clean_snippet)
                norm_chunk = normalize_snippet(target_chunk.content)

                if norm_snippet in norm_chunk:
                    verified_snippet = clean_snippet
                else:
                    if self.require_snippet_containment:
                        logger.warning(
                            "Rejected citation for chunk %s due to hallucinated snippet: %r",
                            candidate.chunk_id,
                            clean_snippet[:80],
                        )
                        rejected_count += 1
                        continue
                    else:
                        logger.info(
                            "Stripped unverified snippet for chunk %s: %r",
                            candidate.chunk_id,
                            clean_snippet[:80],
                        )
                        verified_snippet = None

            # Rule 3: Hydrate verified citation with database-backed source metadata
            citation = Citation(
                chunk_id=target_chunk.chunk_id,
                document_id=target_chunk.document_id,
                original_filename=target_chunk.original_filename,
                page_number=target_chunk.page_number,
                section=target_chunk.section,
                quoted_snippet=verified_snippet,
            )

            validated.append(citation)
            seen_chunk_ids.add(candidate.chunk_id)

        return validated, rejected_count
