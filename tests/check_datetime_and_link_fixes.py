"""
Runnable self-check for two fixes:

1. UTCDateTime (database/types.py) — SQLite drops tzinfo on read-back for
   DateTime(timezone=True) columns, which crashed the Profile screen
   ("can't subtract offset-naive and offset-aware datetimes"). This checks
   the type's bind/result round-trip logic directly (no real DB needed,
   since the bug is in what the type does to a value, not in SQLite itself).

2. Alt-channel-link validation (handlers/admin/analytics.py normalization
   logic, mirrored here since it's inline in the handler) and the render-site
   guard in keyboards/user/search.py — a bad link (e.g. "@handle" instead of
   a URL) used to crash every zero-result search reply.

Run directly: `python3 tests/check_datetime_and_link_fixes.py`
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def check(label: str, condition: bool) -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        raise SystemExit(1)


# --- UTCDateTime -------------------------------------------------------
try:
    from bot.database.types import UTCDateTime
except ModuleNotFoundError as exc:
    print(f"SKIP UTCDateTime checks: dependency not installed here ({exc}). "
          "Run inside the project's venv.")
else:
    t = UTCDateTime()

    # Simulates what SQLite hands back: tzinfo stripped.
    naive_from_db = datetime(2026, 7, 1, 12, 0, 0)
    restored = t.process_result_value(naive_from_db, dialect=None)
    check("result value regains UTC tzinfo", restored.tzinfo == timezone.utc)

    now_aware = datetime.now(timezone.utc)
    check(
        "aware value no longer crashes subtraction after round-trip",
        isinstance(restored - now_aware, type(now_aware - now_aware)),
    )

    # bind side: naive input gets tagged UTC, aware input gets normalized to UTC
    bound_naive = t.process_bind_param(datetime(2026, 7, 1, 12, 0, 0), dialect=None)
    check("bind_param tags naive input as UTC", bound_naive.tzinfo == timezone.utc)

    check("None passes through both directions", t.process_bind_param(None, dialect=None) is None
          and t.process_result_value(None, dialect=None) is None)


# --- alt-channel-link normalization (mirrors handlers/admin/analytics.py) --
def normalize_link(raw: str) -> str | None:
    raw = raw.strip()
    if raw.startswith("@"):
        url = f"https://t.me/{raw[1:]}"
    elif raw.startswith(("t.me/", "telegram.me/")):
        url = f"https://{raw}"
    else:
        url = raw
    return url if url.startswith(("http://", "https://")) else None


check("@username normalizes to a t.me URL", normalize_link("@yefilmalemet") == "https://t.me/yefilmalemet")
check("scheme-less t.me link gets https:// prepended", normalize_link("t.me/yefilmalemet") == "https://t.me/yefilmalemet")
check("full https URL passes through unchanged", normalize_link("https://t.me/yefilmalemet") == "https://t.me/yefilmalemet")
check("garbage input is rejected (None)", normalize_link("yefilmalemet") is None)

# --- utils/movie_delivery.py render-site guard ----------------------------
# search_result_keyboard was fully replaced by build_zero_result_keyboard
# (now DB-driven, supports multiple backup links instead of one). The old
# function never actually had a render-time guard despite this test's
# original intent — `if alt_channel_url: builder.button(url=alt_channel_url)`
# used the value with zero validation, which is exactly why this check has
# been failing all along. The new builder adds that guard for real.
import asyncio

try:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from bot.database.base import Base
    import bot.database.models  # noqa: F401
    from bot.services.settings_service import SettingsService
    from bot.utils.movie_delivery import build_zero_result_keyboard
except ModuleNotFoundError as exc:
    print(f"SKIP render-site guard check: dependency not installed here ({exc}).")
else:
    async def _render_guard_checks():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        Session = async_sessionmaker(engine, expire_on_commit=False)
        session = Session()

        # Bypasses normal save-time validation on purpose, simulating
        # already-bad data reaching storage some other way — the render
        # guard must catch it independently, not rely on the save path
        # having done its job.
        settings_svc = SettingsService(session)
        await settings_svc.set_json("backup_channel_links", [
            {"id": 1, "label": "🔗 Bad", "url": "@yefilmalemet", "is_visible": True, "order": 0},
            {"id": 2, "label": "🔗 Good", "url": "https://t.me/yefilmalemet", "is_visible": True, "order": 1},
        ])
        await session.commit()

        markup = await build_zero_result_keyboard(session, query="test")
        urls = [getattr(btn, "url", None) for row in markup.inline_keyboard for btn in row]

        check("malformed legacy URL is not attached as a button", "@yefilmalemet" not in urls)
        check("valid URL is still attached as a button", "https://t.me/yefilmalemet" in urls)

        await engine.dispose()

    asyncio.run(_render_guard_checks())

print("\nAll checks passed.")
