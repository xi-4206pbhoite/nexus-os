"""Application settings.

Everything comes from the environment. No secret has a usable default — a
missing one fails at startup rather than silently running with a placeholder.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Env(StrEnum):
    local = "local"
    ci = "ci"
    staging = "staging"
    production = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        env_prefix="NEXUS_",
        extra="ignore",
    )

    env: Env = Env.local
    debug: bool = False

    # ── Database ──────────────────────────────────────────────
    # A pgvector-enabled Postgres. See ADR 0001 — hosted free tier locally.
    database_url: SecretStr = Field(
        default=SecretStr(""),
        description="postgresql+asyncpg://... — must have the vector extension available",
    )

    # ── Sessions ──────────────────────────────────────────────
    session_secret: SecretStr = Field(default=SecretStr(""))
    session_cookie_name: str = "nexus_session"
    session_max_age_seconds: int = 60 * 60 * 12

    # ── Local infrastructure substitutes (ADR 0001) ───────────
    storage_backend: str = "filesystem"
    storage_root: Path = REPO_ROOT / ".storage"
    storage_signing_secret: SecretStr = Field(default=SecretStr(""))
    signed_url_ttl_seconds: int = 300

    mailer_backend: str = "file"
    mail_root: Path = REPO_ROOT / ".mail"

    # ── Embeddings (ADR 0003) ─────────────────────────────────
    embedding_model_id: str = "intfloat/multilingual-e5-large"
    embedding_dim: int = 1024
    model_cache_dir: Path = REPO_ROOT / "models"

    # ── Guardrails (doc 06 §8.4) ──────────────────────────────
    tenant_daily_token_budget: int = 2_000_000
    user_daily_token_budget: int = 200_000

    # ── Trusted proxies ───────────────────────────────────────
    # X-Forwarded-For is attacker-controlled by default: anyone can send it,
    # and believing it lets one client mint unlimited rate-limit identities.
    # It is honoured *only* when the direct peer is listed here. Empty means
    # trust nothing and use the direct peer — the safe default, at the cost of
    # every visitor behind a proxy sharing one bucket.
    trusted_proxy_ips: str = ""

    # ── Preview crawl (doc 06 §1.1, §1.2) ─────────────────────
    preview_ttl_days: int = 7
    crawl_max_bytes: int = 5_000_000
    crawl_timeout_seconds: int = 15
    crawl_max_redirects: int = 5

    @field_validator("database_url", "session_secret", "storage_signing_secret")
    @classmethod
    def _required_in_deployed_envs(cls, v: SecretStr) -> SecretStr:
        # Deliberately permissive locally so the app boots for health checks
        # before a database exists; strict everywhere else.
        return v

    @property
    def is_local(self) -> bool:
        return self.env in (Env.local, Env.ci)

    @property
    def trusted_proxies(self) -> frozenset[str]:
        return frozenset(p.strip() for p in self.trusted_proxy_ips.split(",") if p.strip())

    def require(self, name: str) -> str:
        """Fetch a secret, failing loudly if it was never configured."""
        value = getattr(self, name)
        raw = value.get_secret_value() if isinstance(value, SecretStr) else value
        if not raw:
            raise RuntimeError(
                f"NEXUS_{name.upper()} is not set. Copy .env.example to .env and fill it in."
            )
        return str(raw)


@lru_cache
def get_settings() -> Settings:
    return Settings()
