"""Ollama-compatible local LLM provider for grounded generative Q&A."""

import json
import logging
import re
import uuid
from typing import List, Optional

import httpx

from app.core.config import settings
from app.rag.generation.base import (
    BaseGeneratorProvider,
    GenerationError,
    GenerationResult,
    RawCitation,
)
from app.rag.generation.extractive_provider import DeterministicExtractiveProvider
from app.rag.generation.prompt_builder import PromptBuilder
from app.schemas.search import SearchResultItem

logger = logging.getLogger("securedocs.qa.ollama")


class OllamaProvider(BaseGeneratorProvider):
    """
    Local LLM generation provider using Ollama's HTTP API.
    Enforces structured JSON output parsing, connection/read timeouts,
    input/output validation, and safe error boundary isolation.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
        fallback_to_extractive: Optional[bool] = None,
        prompt_builder: Optional[PromptBuilder] = None,
        http_client: Optional[httpx.Client] = None,
        extractive_fallback_provider: Optional[BaseGeneratorProvider] = None,
    ):
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model = model or settings.OLLAMA_MODEL
        self.timeout = float(timeout if timeout is not None else settings.OLLAMA_TIMEOUT_SECONDS)
        self.fallback_to_extractive = (
            fallback_to_extractive
            if fallback_to_extractive is not None
            else settings.OLLAMA_FALLBACK_TO_EXTRACTIVE
        )
        self.prompt_builder = prompt_builder or PromptBuilder()
        self._http_client = http_client
        self._extractive_fallback_provider = (
            extractive_fallback_provider or DeterministicExtractiveProvider()
        )

    @property
    def name(self) -> str:
        return "ollama"

    def _execute_fallback(
        self,
        question: str,
        retrieved_chunks: List[SearchResultItem],
        reason: str,
    ) -> GenerationResult:
        """
        Execute deterministic extractive fallback when explicitly configured.
        Guarantees that the returned provider name reflects 'deterministic_extractive'
        so the system never misrepresents an extractive fallback as an LLM output.
        """
        logger.warning(
            "Ollama generation failed (%s); executing fallback to deterministic extractive provider.",
            reason,
        )
        return self._extractive_fallback_provider.generate(
            question=question,
            retrieved_chunks=retrieved_chunks,
        )

    def generate(
        self,
        question: str,
        retrieved_chunks: List[SearchResultItem],
    ) -> GenerationResult:
        """
        Generate a grounded answer using the local Ollama LLM with structured JSON parsing.
        """
        # Step 1: Pre-check evidence presence
        if not retrieved_chunks:
            return GenerationResult(
                answer="Insufficient evidence: I could not find sufficient evidence in your authorized documents to answer this question.",
                citations=[],
                insufficient_evidence=True,
                provider=self.name,
            )

        messages = self.prompt_builder.build_ollama_messages(
            question=question,
            retrieved_chunks=retrieved_chunks,
        )

        endpoint = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.0,
            },
        }

        # Step 2: Dispatch HTTP request with finite timeouts
        timeout_config = httpx.Timeout(self.timeout, connect=min(5.0, self.timeout))

        try:
            if self._http_client is not None:
                response = self._http_client.post(endpoint, json=payload, timeout=timeout_config)
            else:
                with httpx.Client(timeout=timeout_config) as client:
                    response = client.post(endpoint, json=payload)

            if response.status_code == 404:
                error_msg = f"Ollama model '{self.model}' was not found on the local server."
                logger.error("%s", error_msg)
                if self.fallback_to_extractive:
                    return self._execute_fallback(question, retrieved_chunks, error_msg)
                raise GenerationError(error_msg)

            if response.is_error:
                error_msg = f"Ollama HTTP error (status {response.status_code})."
                logger.error("%s Detail: %s", error_msg, response.text[:200])
                if self.fallback_to_extractive:
                    return self._execute_fallback(question, retrieved_chunks, error_msg)
                raise GenerationError(error_msg)

            # Step 3: Parse HTTP response envelope
            try:
                envelope = response.json()
            except Exception as e:
                error_msg = "Ollama returned a malformed, non-JSON HTTP response body."
                logger.error("%s: %s", error_msg, e)
                if self.fallback_to_extractive:
                    return self._execute_fallback(question, retrieved_chunks, error_msg)
                raise GenerationError(error_msg) from e

            if not isinstance(envelope, dict) or "message" not in envelope or not isinstance(envelope["message"], dict):
                error_msg = "Ollama response envelope missing expected 'message' object."
                logger.error("%s Envelope keys: %s", error_msg, list(envelope.keys()) if isinstance(envelope, dict) else type(envelope))
                if self.fallback_to_extractive:
                    return self._execute_fallback(question, retrieved_chunks, error_msg)
                raise GenerationError(error_msg)

            raw_content = envelope["message"].get("content", "")
            if not isinstance(raw_content, str) or not raw_content.strip():
                error_msg = "Ollama returned an empty message content."
                logger.error("%s", error_msg)
                if self.fallback_to_extractive:
                    return self._execute_fallback(question, retrieved_chunks, error_msg)
                raise GenerationError(error_msg)

            # Step 4: Parse structured JSON payload produced by model
            cleaned_content = raw_content.strip()
            # Strip markdown code blocks if the model wrapped its JSON output
            fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned_content, re.DOTALL)
            if fence_match:
                cleaned_content = fence_match.group(1).strip()

            try:
                model_data = json.loads(cleaned_content)
            except Exception as e:
                error_msg = "Ollama message content was not valid JSON."
                logger.error("%s Raw content preview: %r", error_msg, cleaned_content[:150])
                if self.fallback_to_extractive:
                    return self._execute_fallback(question, retrieved_chunks, error_msg)
                raise GenerationError(error_msg) from e

            if not isinstance(model_data, dict):
                error_msg = "Ollama JSON content is not a dictionary."
                logger.error("%s", error_msg)
                if self.fallback_to_extractive:
                    return self._execute_fallback(question, retrieved_chunks, error_msg)
                raise GenerationError(error_msg)

            raw_answer = model_data.get("answer")
            if not isinstance(raw_answer, str) or not raw_answer.strip():
                error_msg = "Ollama JSON response missing required 'answer' string."
                logger.error("%s", error_msg)
                if self.fallback_to_extractive:
                    return self._execute_fallback(question, retrieved_chunks, error_msg)
                raise GenerationError(error_msg)

            answer = raw_answer.strip()
            insufficient_evidence = bool(model_data.get("insufficient_evidence", False))
            if "insufficient evidence" in answer.lower():
                insufficient_evidence = True

            # Step 5: Parse candidate citations
            raw_citations: List[RawCitation] = []
            candidate_list = model_data.get("citations", [])
            if isinstance(candidate_list, list):
                for item in candidate_list:
                    if not isinstance(item, dict):
                        continue
                    raw_id = item.get("chunk_id")
                    if not raw_id:
                        continue
                    try:
                        chunk_uuid = uuid.UUID(str(raw_id).strip())
                    except (ValueError, AttributeError):
                        logger.warning("Skipping unparseable citation chunk_id from model: %r", raw_id)
                        continue

                    raw_snippet = item.get("quoted_snippet")
                    snippet = str(raw_snippet).strip() if raw_snippet else None

                    raw_citations.append(
                        RawCitation(
                            chunk_id=chunk_uuid,
                            quoted_snippet=snippet,
                        )
                    )

            return GenerationResult(
                answer=answer,
                citations=raw_citations,
                insufficient_evidence=insufficient_evidence,
                provider=self.name,
            )

        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            error_msg = "Local LLM provider is currently unavailable (connection failed)."
            logger.error("Failed to connect to Ollama at %s: %s", self.base_url, e)
            if self.fallback_to_extractive:
                return self._execute_fallback(question, retrieved_chunks, error_msg)
            raise GenerationError(error_msg) from e

        except (httpx.ReadTimeout, httpx.TimeoutException) as e:
            error_msg = "Local LLM provider request timed out."
            logger.error("Ollama request timed out after %.1fs: %s", self.timeout, e)
            if self.fallback_to_extractive:
                return self._execute_fallback(question, retrieved_chunks, error_msg)
            raise GenerationError(error_msg) from e

        except GenerationError:
            # Re-raise explicit GenerationError if fallback was not active
            raise

        except Exception as e:
            error_msg = "Local LLM generation encountered an unexpected error."
            logger.error("Unexpected error in OllamaProvider: %s", e)
            if self.fallback_to_extractive:
                return self._execute_fallback(question, retrieved_chunks, error_msg)
            raise GenerationError(error_msg) from e
