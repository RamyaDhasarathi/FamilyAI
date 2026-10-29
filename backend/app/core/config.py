"""Application configuration via environment variables."""
from __future__ import annotations

import os
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"),
            ".env",
        ),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    APP_ENV: str = "development"
    APP_NAME: str = "Family OS"
    APP_VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./family_os.db"

    # Authentication
    JWT_SECRET_KEY: str = "REPLACE_WITH_A_GENERATED_SECRET"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours for comfortable active sessions
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Bootstrap
    BOOTSTRAP_ADMIN_EMAIL: str = "admin@familyos.local"
    BOOTSTRAP_ADMIN_PASSWORD: str = "REPLACE_WITH_STRONG_PASSWORD"
    BOOTSTRAP_ADMIN_DISPLAY_NAME: str = "Family Admin"
    BOOTSTRAP_FAMILY_NAME: str = "My Family"
    BOOTSTRAP_TOKEN: str = "REPLACE_WITH_ONE_TIME_BOOTSTRAP_TOKEN"

    # LLM Provider
    LLM_PROVIDER: str = "mock"
    LLM_BASE_URL: str = "http://127.0.0.1:11434/v1"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "llama3.2"
    LLM_TIMEOUT_SECONDS: int = 60
    ENABLE_EXTERNAL_CLOUD_INFERENCE: bool = False

    # Product Provider
    PRODUCT_PROVIDER: str = "real_marketplace"

    # Speech-to-text
    STT_PROVIDER: str = "disabled"
    STT_MODEL_PATH: str = ""
    STT_MODEL_NAME: str = "base"
    ENABLE_EXTERNAL_SPEECH: bool = False

    # Text-to-speech
    TTS_PROVIDER: str = "disabled"

    # Audio limits
    MAX_AUDIO_DURATION_SECONDS: int = 60
    MAX_AUDIO_UPLOAD_MB: int = 25

    # Execution
    ALLOW_DEVELOPMENT_SIMULATION: bool = True

    # Qwen Mobile Use Agent
    QWEN_AGENT_ENABLED: bool = True
    QWEN_AGENT_MODE: str = "simulation"  # "simulation", "vlm_direct", "adb_bridge"
    QWEN_VLM_BASE_URL: str = "http://127.0.0.1:11434/v1"
    QWEN_VLM_MODEL: str = "qwen2.5-vl:7b"
    QWEN_VLM_API_KEY: str = ""
    QWEN_VLM_TIMEOUT_SECONDS: int = 60
    ADB_DEVICE_SERIAL: str = ""
    ADB_BINARY_PATH: str = ""

    # CORS
    CORS_ORIGINS: str = ""

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development"

    @property
    def cors_origins_list(self) -> List[str]:
        if not self.CORS_ORIGINS:
            return ["*"] if self.is_development else []
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    def validate_production(self) -> None:
        """Raise on insecure production config."""
        if not self.is_development:
            if self.JWT_SECRET_KEY.startswith("REPLACE_"):
                raise ValueError("JWT_SECRET_KEY must be set in production")
            if self.BOOTSTRAP_ADMIN_PASSWORD.startswith("REPLACE_"):
                raise ValueError("BOOTSTRAP_ADMIN_PASSWORD must be set")
            if not self.CORS_ORIGINS:
                raise ValueError("CORS_ORIGINS must be set in production")


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
        if not _settings.is_development:
            _settings.validate_production()
    return _settings
