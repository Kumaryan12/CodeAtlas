from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from codeatlas.ai.usage import TokenPrices

PROJECT_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CODEATLAS_", env_file=PROJECT_ROOT / ".env", extra="ignore"
    )

    database_url: SecretStr = SecretStr(
        "postgresql+psycopg://codeatlas:codeatlas_local@localhost:5432/codeatlas"
    )

    workspace_root: Path = PROJECT_ROOT / "workspaces"
    max_download_bytes: int = Field(default=20 * 1024 * 1024, ge=1024, le=100 * 1024 * 1024)
    download_timeout_seconds: int = Field(default=45, ge=1, le=60)
    analysis_timeout_seconds: int = Field(default=60, ge=1, le=60)

    reasoning_provider: Literal["anthropic", "openai"] = "anthropic"
    anthropic_api_key: SecretStr = SecretStr("")
    openai_api_key: SecretStr = SecretStr("")
    embedding_model: str = Field(default="text-embedding-3-small", min_length=1, max_length=100)
    answer_model: str | None = Field(default=None, min_length=1, max_length=100)

    @property
    def reasoning_model(self) -> str:
        return self.answer_model or (
            "claude-sonnet-5" if self.reasoning_provider == "anthropic" else "gpt-4.1-mini"
        )

    @property
    def reasoning_configured(self) -> bool:
        key = (
            self.anthropic_api_key
            if self.reasoning_provider == "anthropic"
            else self.openai_api_key
        )
        return bool(key.get_secret_value().strip())

    @property
    def reasoning_key_name(self) -> str:
        return (
            "CODEATLAS_ANTHROPIC_API_KEY"
            if self.reasoning_provider == "anthropic"
            else "CODEATLAS_OPENAI_API_KEY"
        )

    usage_prices: dict[str, TokenPrices] = Field(default_factory=dict)
    read_tool_transport: Literal["local", "mcp"] = "local"
    sandbox_enabled: bool = False
