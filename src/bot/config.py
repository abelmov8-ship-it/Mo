from __future__ import annotations

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # ── Bot ───────────────────────────────────────────────────────────────────
    BOT_TOKEN: SecretStr
    ADMIN_IDS: list[int] = []

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = "sqlite+aiosqlite:///./bot.db"

    # ── Chapa ─────────────────────────────────────────────────────────────────
    CHAPA_ENABLED: bool = False
    CHAPA_SECRET_KEY: SecretStr | None = None
    CHAPA_BASE_URL: str = "https://api.chapa.co/v1"
    # Webhook secret configured in the Chapa dashboard — verifies inbound
    # webhook requests are actually from Chapa. Leave unset to disable the
    # webhook (manual "Verify" tap keeps working either way).
    CHAPA_WEBHOOK_SECRET: SecretStr | None = None
    # Public HTTPS origin the bot is reachable at (e.g. https://bot.example.com),
    # used to build the Chapa webhook callback_url. Leave unset to skip
    # sending Chapa a callback_url at all (falls back to manual verify only).
    PUBLIC_BASE_URL: str | None = None
    # Port the webhook server listens on — put a reverse proxy / PaaS router
    # in front of it for HTTPS; this process itself only speaks plain HTTP.
    WEBHOOK_PORT: int = 8080

    # ── Wallet & PPV ──────────────────────────────────────────────────────────
    WALLET_TOPUP_ENABLED: bool = True

    # ── Anti-Spam ─────────────────────────────────────────────────────────────
    ANTI_SPAM_THRESHOLD: int = 5          # max updates/second before lockout
    ANTI_SPAM_LOCKOUT_SECONDS: int = 30

    # ── Delete Timer ──────────────────────────────────────────────────────────
    DELETE_TIMER_MINUTES: int = 3         # 0 = never

    # ── Referral ─────────────────────────────────────────────────────────────
    REFERRAL_MILESTONE: int = 5
    REFERRAL_REWARD_DAYS: int = 3

    # ── Backup ────────────────────────────────────────────────────────────────
    BACKUP_CHANNEL_ID: int | None = None

    # ── Links ─────────────────────────────────────────────────────────────────
    SUPPORT_USERNAME: str | None = None

    # ── Maintenance ───────────────────────────────────────────────────────────
    MAINTENANCE_MODE: bool = False

    # ── Keyboard type toggles ─────────────────────────────────────────────────
    # "reply" or "inline". Default "inline" preserves current behavior for
    # every existing deployment — this must not change what anyone sees
    # until an admin explicitly opts in via Core Config.
    CHANNELS_KEYBOARD_TYPE: str = "inline"
    PAYMENT_KEYBOARD_TYPE: str = "inline"

    @field_validator("ADMIN_IDS", mode="before")
    @classmethod
    def parse_admin_ids(cls, v: str | int | list) -> list[int]:
        # ponytail: a single-admin .env value like ADMIN_IDS=123456789 has no
        # comma, so it's valid JSON — pydantic-settings' env source JSON-decodes
        # it into a bare int *before* this validator runs, and that int used
        # to fall through every branch below to `[]`, silently dropping the
        # only configured admin. Multi-ID comma lists never hit this (they
        # aren't valid JSON, so they arrive here as the raw string).
        if isinstance(v, list):
            return v
        if isinstance(v, int):
            return [v]
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        return []


settings = Settings()
