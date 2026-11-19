"""Runtime configuration loaded from environment variables or defaults."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Application settings for Local-First execution and Cloud adapter migration."""

    model_config = SettingsConfigDict(
        env_prefix="TOPO_LOGIC_",
        env_file=".env",
        extra="ignore",
    )

    data_dir: Path = Field(default=Path(".topo_logic_data"))
    host: str = Field(default="127.0.0.1")
    port: int = Field(default=8000, ge=1, le=65535)
    max_upload_mb: int = Field(default=100, ge=1, le=2048)
    max_workers: int = Field(default=2, ge=1, le=64)
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def db_path(self) -> Path:
        return self.data_dir / "topo_logic.db"

    @property
    def artifacts_dir(self) -> Path:
        return self.data_dir / "artifacts"
