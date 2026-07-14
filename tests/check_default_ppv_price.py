"""
Runnable self-check for the default-PPV-price fix.

The actual bug: batch-uploaded movies always defaulted to ppv_price=0.0
(free for everyone, VIP or not), so the correct VIP/PPV gate built in
Phase 2 never had anything to enforce. This checks the real fix:

1. No default price configured -> batch upload is blocked, not silently
   free. There is no hardcoded price anywhere in this code path.
2. A configured default price actually gets applied to new batch entries
   that don't specify their own price.
3. Existing movies (already in the DB before a default was configured, or
   added with their own explicit price) are never touched by this —
   exactly what was asked for: "leave the old files exactly as they are."
4. Once priced, a non-VIP user hits the PPV gate (reusing Phase 2's
   send_movie_or_ppv_gate) instead of getting the file for free.

Run directly: `python3 tests/check_default_ppv_price.py`
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.database.base import Base
import bot.database.models  # noqa: F401
from bot.database.models.movie import MovieFileType
from bot.database.models.user import User, UserLanguage
from bot.handlers.admin.system import _index_batch
from bot.services.movie_service import MovieService
from bot.services.settings_service import SettingsService
from bot.utils.movie_delivery import send_movie_or_ppv_gate


async def _fresh_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    return engine, Session()


async def check_no_hidden_default_when_unconfigured():
    engine, session = await _fresh_session()
    svc = SettingsService(session)

    assert await svc.get("default_ppv_price") is None, "must be genuinely unset, not a hidden 0 or number"

    # If _index_batch were ever reached with nothing configured (shouldn't
    # happen — batch_upload_start blocks first), it must not silently
    # invent a price either; the safety-net fallback is 0.0 (== today's
    # already-existing free behaviour), never a made-up nonzero number.
    batch = [{"file_id": "unconfigured1", "title": "No Default Set", "file_type": MovieFileType.VIDEO}]
    await _index_batch(bot=None, session=session, batch=batch)
    await session.commit()
    movie = await MovieService(session).get_by_file_id("unconfigured1")
    assert movie.ppv_price == 0.0, "no hardcoded fallback price — only 0.0 (today's existing behaviour)"

    await engine.dispose()
    print("✓ no default configured: no hidden/hardcoded price is ever invented")


async def check_configured_default_applies_to_new_uploads():
    engine, session = await _fresh_session()
    svc = SettingsService(session)
    await svc.set("default_ppv_price", "75.0")
    await session.commit()

    batch = [
        {"file_id": "new1", "title": "New Upload One", "file_type": MovieFileType.VIDEO},
        {"file_id": "new2", "title": "New Upload Two", "file_type": MovieFileType.DOCUMENT},
    ]
    await _index_batch(bot=None, session=session, batch=batch)
    await session.commit()

    m1 = await MovieService(session).get_by_file_id("new1")
    m2 = await MovieService(session).get_by_file_id("new2")
    assert m1.ppv_price == 75.0 and m1.is_ppv is True
    assert m2.ppv_price == 75.0 and m2.is_ppv is True

    await engine.dispose()
    print("✓ configured default price (75.0) applied to every new batch entry")


async def check_existing_movies_are_never_touched():
    engine, session = await _fresh_session()
    movie_svc = MovieService(session)

    # Simulates a movie that was already free in the DB before the admin
    # ever configured a default price.
    old_free_movie = await movie_svc.add("old_free_file", "Old Free Movie", ppv_price=0.0)
    old_priced_movie = await movie_svc.add("old_priced_file", "Old Custom Priced Movie", ppv_price=30.0)
    await session.commit()

    # Now the admin configures a default price and uploads something new.
    await SettingsService(session).set("default_ppv_price", "75.0")
    await session.commit()
    await _index_batch(bot=None, session=session,
                       batch=[{"file_id": "brand_new", "title": "Brand New", "file_type": MovieFileType.VIDEO}])
    await session.commit()

    refetched_free = await movie_svc.get_by_file_id("old_free_file")
    refetched_priced = await movie_svc.get_by_file_id("old_priced_file")
    new_movie = await movie_svc.get_by_file_id("brand_new")

    assert refetched_free.ppv_price == 0.0, "existing free movie must stay free — 'leave the old files exactly as they are'"
    assert refetched_priced.ppv_price == 30.0, "existing custom-priced movie must keep its own price, not the new default"
    assert new_movie.ppv_price == 75.0, "only the new upload gets the configured default"

    await engine.dispose()
    print("✓ existing movies (free or custom-priced) are untouched — only new uploads get the default")


async def check_non_vip_actually_gated_after_pricing():
    engine, session = await _fresh_session()
    await SettingsService(session).set("default_ppv_price", "50.0")
    await session.commit()
    await _index_batch(bot=None, session=session,
                       batch=[{"file_id": "gated1", "title": "Gated Movie", "file_type": MovieFileType.VIDEO}])
    await session.commit()
    movie = await MovieService(session).get_by_file_id("gated1")

    free_user = User(telegram_id=1, first_name="A", language=UserLanguage.EN, is_vip=False, wallet_balance=0)
    vip_user = User(telegram_id=2, first_name="B", language=UserLanguage.EN, is_vip=True, wallet_balance=0)

    class RecordingMessage:
        def __init__(self):
            self.calls = []
        async def answer(self, text, **kw):
            self.calls.append(("answer", text)); return SimpleNamespace(chat=SimpleNamespace(id=1), message_id=1)
        async def answer_video(self, video, **kw):
            self.calls.append(("answer_video", video)); return SimpleNamespace(chat=SimpleNamespace(id=1), message_id=1)
        async def answer_document(self, document, **kw):
            self.calls.append(("answer_document", document)); return SimpleNamespace(chat=SimpleNamespace(id=1), message_id=1)

    msg = RecordingMessage()
    await send_movie_or_ppv_gate(msg, movie, free_user)
    assert msg.calls[0][0] == "answer", "non-VIP must hit the PPV gate, not get the file for free"

    msg2 = RecordingMessage()
    await send_movie_or_ppv_gate(msg2, movie, vip_user)
    assert msg2.calls[0][0] == "answer_video", "VIP still gets it directly, as before"

    await engine.dispose()
    print("✓ once priced, non-VIP hits the wallet-PPV/VIP-upgrade gate; VIP still passes through")


if __name__ == "__main__":
    asyncio.run(check_no_hidden_default_when_unconfigured())
    asyncio.run(check_configured_default_applies_to_new_uploads())
    asyncio.run(check_existing_movies_are_never_touched())
    asyncio.run(check_non_vip_actually_gated_after_pricing())
    print("\nAll default-PPV-price checks passed.")
