"""Application settings.

Everything comes from the environment. No secret has a usable default — a
missing one fails at startup rather than silently running with a placeholder.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, model_validator
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

    env: Env
    """Required, with no default, and that is the fix for a real failure.

    It defaulted to `local`, and `is_local` also answered true for `ci`. So a
    deployment that simply forgot `NEXUS_ENV` served `/docs` and
    `/openapi.json` publicly and set `secure=False` on both the session and the
    CSRF cookie, over the internet, on a product holding company financials.
    Nothing failed and nothing logged.

    The plan offered two fixes — drop `ci` from `is_local`, or make cookie
    security independent of it. Neither addresses the default, which is what
    turned a forgotten variable into insecure cookies. So there is no default:
    a missing `NEXUS_ENV` is a startup error naming the variable, rather than a
    silent choice of the most permissive environment. See ADR 0015.
    """

    debug: bool = False

    # ── Database ──────────────────────────────────────────────
    # A pgvector-enabled Postgres. See ADR 0001 — hosted free tier locally.
    database_url: SecretStr = Field(
        default=SecretStr(""),
        description="postgresql+asyncpg://... — must have the vector extension available",
    )
    db_transaction_pooler: bool = False
    """Whether the URL points at a transaction-mode pooler.

    Was inferred from `"-pooler" in url`, which is a guess about a hostname: it
    is true of Neon's pooled endpoint and of nothing else. PgBouncer in front of
    RDS, a Cloud SQL proxy, or Neon renaming the endpoint all leave it silently
    false — and the failure it prevents is `prepared statement ... does not
    exist` appearing only under concurrency."""

    db_statement_timeout: str = "15s"
    """Bounds a single query. A request that hangs otherwise holds one of five
    pooled connections until the process restarts."""

    db_lock_timeout: str = "5s"
    """Bounds *waiting* for a lock, which the statement timeout does not: a
    statement blocked on a lock has not begun executing."""

    db_idle_in_transaction_timeout: str = "30s"
    """Bounds an open transaction doing nothing — the shape a request that died
    mid-flight leaves behind, and the one that blocks every later migration."""

    db_command_timeout_seconds: float = 20.0
    """asyncpg's own, client-side. It still fires when the server is
    unreachable rather than merely slow, which a server-side timeout cannot."""

    db_pool_timeout_seconds: float = 10.0
    """How long a request waits for a connection from the pool before failing.
    SQLAlchemy's default is 30s, which is longer than most callers will wait."""

    # ── Sessions ──────────────────────────────────────────────
    #
    # There is deliberately no `session_secret`. One was declared here,
    # documented in `.env.example`, required by the validator below, pinned in
    # `conftest.py` — and read by no line of code in the repository. A
    # required-looking secret that nothing reads is worse than none: it teaches
    # whoever provisions the environment that the list of secrets is
    # approximate.
    #
    # Nothing signs a session token because there is nothing to sign. The token
    # is 256 bits of CSPRNG output and only its SHA-256 hash is stored, so
    # presenting it is authenticated by the lookup itself; an HMAC over a random
    # opaque string adds no property. See `app/auth/tokens.py` and ADR 0015.
    session_cookie_name: str = "nexus_session"
    session_max_age_seconds: int = 60 * 60 * 12

    # ── Local infrastructure substitutes (ADR 0001) ───────────
    storage_backend: str = "filesystem"
    storage_root: Path = REPO_ROOT / ".storage"
    storage_signing_secret: SecretStr = Field(default=SecretStr(""))
    signed_url_ttl_seconds: int = 300

    # ── Email (P3) ────────────────────────────────────────────
    # `file` writes RFC-822 `.eml` files to `mail_root`; `smtp` sends. The file
    # backend is not a stub — it is what makes the whole verification and
    # invitation chain testable end to end with no provider and no account, so
    # **D4 gates deployment rather than development**.
    mailer_backend: str = "file"
    mail_root: Path = REPO_ROOT / ".mail"

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: SecretStr = Field(default=SecretStr(""))
    smtp_from: str = "NEXUS OS <no-reply@nexusos.local>"
    # STARTTLS on the port above. Off only for a local relay, and the validator
    # refuses that combination in a deployed environment.
    smtp_tls: bool = True

    # Where the links in those emails point. Not derived from the request:
    # `Host` is attacker-controlled, and a verification link built from it is a
    # working account-takeover primitive — the attacker registers, receives a
    # link to their own host, and harvests the token when the real owner clicks.
    public_base_url: str = "http://localhost:3000"

    # ── Embeddings (ADR 0003) ─────────────────────────────────
    embedding_model_id: str = "intfloat/multilingual-e5-large"
    embedding_dim: int = 1024
    model_cache_dir: Path = REPO_ROOT / "models"
    embeddings_enabled: bool = True
    """Environment-level off switch, separate from the library being absent.

    Same distinction as `ai_enabled`: "not installed yet" and "deliberately
    switched off" are different messages to a user. An absent library is never
    an error — the model is a ~2GB download and running without it is a
    supported state, in which documents still upload, parse and classify but are
    not yet searchable."""

    # ── Language model (ADR 0011) ─────────────────────────────
    # Deliberately has no usable default and is NOT passed through `require()`.
    # Every other secret here fails loudly when absent because the application
    # cannot work without it; this one is different — an empty key is a
    # supported operating state. `app/ai/registry.py` returns a provider that
    # reports `unconfigured` and the product runs without AI features.
    anthropic_api_key: SecretStr = Field(default=SecretStr(""))
    anthropic_model: str = "claude-sonnet-4-5"
    ai_enabled: bool = True
    """Environment-level off switch, separate from the key being absent.
    Distinguishes "not configured yet" from "deliberately switched off"."""

    disabled_ai_skills: str = ""
    """Comma-separated skill names — the per-skill kill switch (doc 07 M8 task
    8.7). Per-skill rather than global so one misbehaving prompt can be stopped
    without taking down every AI feature in the product."""

    # ── Guardrails (doc 06 §8.4) ──────────────────────────────
    tenant_daily_token_budget: int = 2_000_000
    user_daily_token_budget: int = 200_000

    # ── Crawl budget (doc 06 §1.2) ────────────────────────────
    # `trusted_proxy_ips` and `preview_ttl_hours` sat here until Phase 2. Both
    # existed only for the unauthenticated audit: the first decided whose
    # `X-Forwarded-For` to believe when rate-limiting anonymous callers, the
    # second bounded how long a third party's crawled data was retained. With
    # no anonymous crawl there is no address to attribute and no third-party
    # data to expire (`doc/11` Q1, D9 void). The limits below survive because a
    # crawl still has to be bounded, whoever asked for it.
    crawl_max_bytes: int = 5_000_000
    crawl_timeout_seconds: int = 15
    crawl_max_redirects: int = 5

    # Secrets the application cannot work without once it is deployed.
    # `anthropic_api_key` is deliberately absent: an empty key is a supported
    # operating state (ADR 0011), and listing it here would turn "no AI yet"
    # into a refusal to boot.
    _DEPLOYED_REQUIRES = ("database_url", "storage_signing_secret")

    @model_validator(mode="after")
    def _required_in_deployed_envs(self) -> Settings:
        """Refuse to start in a deployed environment with a secret missing.

        This replaces a `field_validator` over the same secrets whose body was
        `return v`. It enforced nothing while presenting as a security control,
        which is worse than its absence, because absence is visible.

        A model validator rather than a field one for two reasons: it can read
        `env` without depending on field declaration order, and it can name
        every missing secret in one error. A deployment fixing them one restart
        at a time is a deployment being told the truth slowly.

        Local and `ci` stay permissive on purpose, so the process boots and
        answers a health check before a database exists. That was always the
        intent; only the enforcement everywhere else was missing.
        """
        if self.env in (Env.local, Env.ci):
            return self

        missing = [
            f"NEXUS_{name.upper()}"
            for name in self._DEPLOYED_REQUIRES
            if not getattr(self, name).get_secret_value()
        ]
        if missing:
            names = " and ".join(missing) if len(missing) < 3 else ", ".join(missing)
            raise ValueError(
                f"NEXUS_ENV={self.env.value} requires {names}, which "
                f"{'is' if len(missing) == 1 else 'are'} empty or unset. These "
                "are only optional in local and ci, where the app must boot "
                "before a database exists."
            )

        # Email is separate from the secret list because what it requires
        # depends on which backend is selected, and because getting it wrong is
        # silent rather than loud: a deployed environment left on the `file`
        # backend writes verification emails to a directory nobody reads, and
        # every new account is stuck unverified with no error anywhere.
        if self.mailer_backend == "file":
            raise ValueError(
                f"NEXUS_ENV={self.env.value} cannot use NEXUS_MAILER_BACKEND=file. "
                "It writes .eml files to disk instead of sending them, so every "
                "verification and invitation would silently go nowhere. Set "
                "smtp, or say so explicitly by pointing mail_root at a volume "
                "someone reads."
            )
        if self.mailer_backend == "smtp" and not self.smtp_host:
            raise ValueError(
                f"NEXUS_ENV={self.env.value} with NEXUS_MAILER_BACKEND=smtp "
                "requires NEXUS_SMTP_HOST."
            )
        if self.mailer_backend == "smtp" and not self.smtp_tls:
            raise ValueError(
                "NEXUS_SMTP_TLS=false sends credentials and every verification "
                "token in clear text. It is allowed in local and ci for a "
                f"local relay; NEXUS_ENV={self.env.value} is not."
            )
        if self.public_base_url.startswith("http://"):
            raise ValueError(
                f"NEXUS_ENV={self.env.value} requires an https NEXUS_PUBLIC_BASE_URL. "
                "Every verification and password-reset link is built from it, so "
                "plain http puts single-use account tokens on the wire."
            )
        return self

    @property
    def cookies_secure(self) -> bool:
        """Whether the session and CSRF cookies carry `Secure`.

        False for `local` and `ci`, which are served over plain HTTP. Safe now
        only because `env` has no default: previously a forgotten `NEXUS_ENV`
        landed here as `local` and produced insecure cookies in production.
        """
        return self.env not in (Env.local, Env.ci)

    @property
    def docs_enabled(self) -> bool:
        """Whether `/docs` and `/openapi.json` are served.

        Narrower than cookie security, and deliberately so. Together they
        enumerate every endpoint and its schema; a developer's machine is the
        only place that is a convenience rather than a disclosure. `ci` is
        excluded — nobody reads `/docs` there.
        """
        return self.env is Env.local

    @property
    def disabled_ai_skills_set(self) -> frozenset[str]:
        return frozenset(s.strip() for s in self.disabled_ai_skills.split(",") if s.strip())

    def require(self, name: str) -> str:
        """Fetch a secret, failing loudly if it was never configured.

        Note `anthropic_api_key` is deliberately never fetched through here. An
        absent language model is a supported state, not a misconfiguration, and
        routing it through `require()` would turn "no AI yet" into a crash.
        """
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
