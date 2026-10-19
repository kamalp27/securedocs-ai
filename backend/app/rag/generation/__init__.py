"""Grounded generation module for SecureDocs AI."""

from typing import Optional, Set
from app.core.config import settings
from app.rag.generation.base import (
    BaseGeneratorProvider,
    GenerationError,
    GenerationResult,
    RawCitation,
)
from app.rag.generation.citation_validator import CitationValidator
from app.rag.generation.extractive_provider import DeterministicExtractiveProvider
from app.rag.generation.mock_provider import MockGeneratorProvider
from app.rag.generation.ollama_provider import OllamaProvider
from app.rag.generation.prompt_builder import (
    GROUNDED_QA_SYSTEM_PROMPT,
    PromptBuilder,
)

VALID_PROVIDERS: Set[str] = {
    "deterministic_extractive",
    "extractive",
    "ollama",
    "local_llm",
    "mock",
    "mock_generator",
}


def get_generator_provider(provider_name: Optional[str] = None) -> BaseGeneratorProvider:
    """
    Factory function returning the configured or requested generator provider.
    Defaults to the deterministic extractive provider for zero-API-key offline execution.
    Validates provider names and rejects unknown values safely.
    """
    target = provider_name if provider_name is not None and provider_name.strip() else settings.DEFAULT_QA_PROVIDER
    normalized = target.lower().strip()

    if normalized not in VALID_PROVIDERS:
        raise GenerationError(
            f"Unsupported generator provider '{provider_name}'. "
            f"Supported providers: 'deterministic_extractive', 'ollama', 'mock'."
        )

    if normalized in ("mock", "mock_generator"):
        return MockGeneratorProvider()

    if normalized in ("ollama", "local_llm"):
        return OllamaProvider()

    # Default to deterministic extractive baseline
    return DeterministicExtractiveProvider()


__all__ = [
    "BaseGeneratorProvider",
    "GenerationError",
    "GenerationResult",
    "RawCitation",
    "CitationValidator",
    "DeterministicExtractiveProvider",
    "MockGeneratorProvider",
    "OllamaProvider",
    "PromptBuilder",
    "GROUNDED_QA_SYSTEM_PROMPT",
    "VALID_PROVIDERS",
    "get_generator_provider",
]