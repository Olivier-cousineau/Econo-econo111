from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, Optional, Sequence

from pydantic import BaseSettings, Field, validator
from pydantic import dotenv_values


BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Application configuration loaded from the environment."""

    base_dir: Path = Field(default=BASE_DIR)
    data_dir: Path = Field(default_factory=lambda: BASE_DIR / "data")
    logs_dir: Path = Field(default_factory=lambda: BASE_DIR / "logs")

    walmart_store_id: str = Field(default="3131")
    walmart_source_file: Path = Field(
        default_factory=lambda: BASE_DIR / "data" / "walmart" / "blainville.json"
    )
    walmart_api_base: str = Field(
        default="https://www.walmart.ca/api/product-page"
    )
    walmart_request_timeout: int = Field(default=10)
    walmart_headers: Dict[str, str] = Field(
        default_factory=lambda: {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
        }
    )

    penny_deal_output_file: Path = Field(
        default_factory=lambda: BASE_DIR
        / "logs"
        / "penny_deals_blainville.json"
    )

    stripe_secret_key: Optional[str] = Field(default=None, env="STRIPE_SECRET_KEY")
    stripe_publishable_key: Optional[str] = Field(
        default=None, env="STRIPE_PUBLISHABLE_KEY"
    )
    stripe_publishable_key_candidates: Sequence[str] = Field(
        default=(
            "STRIPE_PUBLISHABLE_KEY",
            "NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY",
            "STRIPE_PUBLIC_KEY",
        )
    )
    stripe_success_url: str = Field(
        default="http://localhost:5000/success?session_id={CHECKOUT_SESSION_ID}",
        env="STRIPE_SUCCESS_URL",
    )
    stripe_cancel_url: str = Field(
        default="http://localhost:5000/cancel", env="STRIPE_CANCEL_URL"
    )

    deals_default_path: Optional[str] = Field(
        default=None, env="DEALS_DEFAULT_PATH"
    )

    class Config:
        env_prefix = ""

    @validator("data_dir", "logs_dir", pre=True)
    def _resolve_relative_dirs(cls, value: object, values: Dict[str, object], field):
        base_dir: Path = values.get("base_dir", BASE_DIR)  # type: ignore[assignment]
        if value in (None, "", False):
            default = field.default_factory() if field.default_factory else field.default
            if isinstance(default, Path):
                return default
            if callable(default):
                produced = default()
                if isinstance(produced, Path):
                    return produced
            return Path(base_dir)
        path = Path(str(value))
        if not path.is_absolute():
            path = (base_dir / path).resolve()
        return path

    @validator("walmart_source_file", "penny_deal_output_file", pre=True)
    def _resolve_relative_files(
        cls, value: object, values: Dict[str, object], field
    ) -> Path:
        base_dir: Path = values.get("base_dir", BASE_DIR)  # type: ignore[assignment]
        if value in (None, "", False):
            default = field.default_factory() if field.default_factory else field.default
            if callable(default):
                produced = default()
                if isinstance(produced, Path):
                    return produced
            if isinstance(default, Path):
                return default
            raise ValueError(f"Unable to compute default for {field.name}")
        path = Path(str(value))
        if not path.is_absolute():
            path = (base_dir / path).resolve()
        return path

    def iter_env_files(self) -> Iterable[Path]:
        for filename in (".env.local", ".env"):
            candidate = self.base_dir / filename
            if candidate.exists() and candidate.is_file():
                yield candidate


@lru_cache()
def get_settings() -> Settings:
    env_files = [
        path for path in (BASE_DIR / ".env.local", BASE_DIR / ".env") if path.exists()
    ]
    kwargs = {}
    if env_files:
        kwargs.update({"_env_file": env_files, "_env_file_encoding": "utf-8"})

    settings = Settings(**kwargs)

    for env_path in env_files:
        values = dotenv_values(env_path, encoding="utf-8")
        for key, value in values.items():
            if key and value is not None and key not in os.environ:
                os.environ[key] = value

    return settings
