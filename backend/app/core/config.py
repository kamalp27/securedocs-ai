"""Application configuration loaded from environment variables."""

from typing import List, Optional
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """SecureDocs AI configuration settings."""

    # Application Metadata
    PROJECT_NAME: str = "SecureDocs AI"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    API_V1_STR: str = "/api/v1"

    # Security & JWT Tokens
    SECRET_KEY: str = "change-me-to-a-secure-random-secret-key-min-32-chars"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ENABLE_HSTS: bool = False

    # Cookie & CSRF Transport Configuration
    REFRESH_COOKIE_NAME: str = "securedocs_refresh_token"
    REFRESH_COOKIE_PATH: str = "/api/v1/auth"
    REFRESH_COOKIE_HTTPONLY: bool = True
    REFRESH_COOKIE_SECURE: bool = False
    REFRESH_COOKIE_SAMESITE: str = "lax"
    REFRESH_COOKIE_DOMAIN: Optional[str] = None

    CSRF_COOKIE_NAME: str = "securedocs_csrf_token"
    CSRF_HEADER_NAME: str = "X-CSRF-Token"
    CSRF_COOKIE_PATH: str = "/"
    CSRF_COOKIE_HTTPONLY: bool = False
    CSRF_COOKIE_SAMESITE: str = "lax"

    # Rate Limiting & Network Safety
    RATE_LIMIT_ENABLED: bool = True
    TRUST_PROXY_HEADERS: bool = False
    TRUSTED_PROXIES: List[str] = ["127.0.0.1", "::1"]

    # Database Connection
    DATABASE_URL: str = "sqlite:///./securedocs.db"

    # Protected File Storage
    UPLOAD_DIR: str = "./data/uploads"
    MAX_UPLOAD_SIZE_BYTES: int = 26214400  # 25 MB
    ALLOWED_MIME_TYPES: List[str] = [
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain",
        "text/markdown",
    ]

    # Vector Store & Embedding Configuration
    FAISS_INDEX_PATH: str = "./data/faiss_indices/securedocs.index"
    EMBEDDING_MODEL_NAME: str = "all-MiniLM-L6-v2"
    EMBEDDING_DEVICE: str = "cpu"
    EMBEDDING_CACHE_DIR: Optional[str] = None
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 50
    SIMILARITY_TOP_K: int = 5
    MAX_SEARCH_TOP_K: int = 50
    SIMILARITY_THRESHOLD: float = 0.45

    # Generative Q&A & Evaluation Benchmarks
    DEFAULT_QA_PROVIDER: str = "deterministic_extractive"
    QA_MAX_QUESTION_LENGTH: int = 1000
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.2"
    OLLAMA_TIMEOUT_SECONDS: float = 30.0
    OLLAMA_FALLBACK_TO_EXTRACTIVE: bool = False
    EVALUATION_DATASET_PATH: str = "./data/evaluation_benchmarks/golden_dataset.json"

    # CORS Settings
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
    ]

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        """
        Enforce fail-closed security for non-development environments.
        Rejects default dummy SECRET_KEY and keys shorter than 32 characters in staging/production.
        """
        is_production_like = self.ENVIRONMENT.lower() in ("production", "staging")
        known_dummy_key = "change-me-to-a-secure-random-secret-key-min-32-chars"

        if "*" in self.BACKEND_CORS_ORIGINS:
            raise ValueError(
                "Insecure configuration: BACKEND_CORS_ORIGINS cannot contain '*' wildcard "
                "when credentialed authentication and cookies are enabled."
            )

        if self.REFRESH_COOKIE_SAMESITE.lower() not in ("lax", "strict", "none"):
            raise ValueError("REFRESH_COOKIE_SAMESITE must be one of: 'lax', 'strict', 'none'")

        if is_production_like:
            if self.SECRET_KEY == known_dummy_key:
                raise ValueError(
                    f"Insecure configuration: Default SECRET_KEY is not permitted in {self.ENVIRONMENT}. "
                    "Generate a cryptographically random secret key (e.g. `openssl rand -hex 32`)."
                )
            if len(self.SECRET_KEY) < 32:
                raise ValueError(
                    f"Insecure configuration: SECRET_KEY must be at least 32 characters in {self.ENVIRONMENT} "
                    f"(got {len(self.SECRET_KEY)} characters). Use `openssl rand -hex 32`."
                )
            # Ensure cookies require HTTPS in staging/production unless explicitly overridden
            self.REFRESH_COOKIE_SECURE = True

        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
