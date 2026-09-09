from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

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

    openai_api_key: SecretStr = SecretStr("")
    embedding_model: str = Field(default="text-embedding-3-small", min_length=1, max_length=100)
    answer_model: str = Field(default="gpt-4.1-mini", min_length=1, max_length=100)
