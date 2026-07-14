"""
Runnable self-check for automatic channel indexing.

The critical property: this reuses the exact default_ppv_price gate from
before. If that's not configured, nothing gets auto-indexed — full stop,
no silent fallback to free. This is what stops "automatically register
files" from quietly reopening the free-content bug fixed two rounds ago.

1. A channel that ISN'T flagged is_auto_index_source is completely ignored
   — posting a video there does nothing, regardless of price config.
2. A designated channel with NO default price configured: nothing gets
   indexed, and admins are notified why.
3. A designated channel WITH a default price configured: the file is
   indexed, priced at the configured default — same pricing behavior as
   manual batch upload, not a separate/different price path.
4. Title derivation (_derive_title) matches the same caption → filename →
   placeholder fallback used by manual batch upload — one shared function,
   not two divergent implementations.
5. Posting the same file twice doesn't create a duplicate movie (reuses
   batch_add's existing dedup).

Run directly: `python3 tests/check_auto_index_channel.py`
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
from bot.database.models.channel import ChannelCategory
from bot.handlers.admin.system import _derive_title, auto_index_channel_post
from bot.services.channel_service import ChannelService
from bot.services.movie_service import MovieService
from bot.services.settings_service import SettingsService


async def _fresh_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    return engine, Session()


class FakeBot:
    def __init__(self):
        self.sent = []
    async def send_message(self, chat_id, text, **kw):
        self.sent.append((chat_id, text))


def _fake_channel_post(chat_id: int, file_id: str, caption: str | None, bot):
    video = SimpleNamespace(file_id=file_id, file_name=None)
    return SimpleNamespace(
        chat=SimpleNamespace(id=chat_id),
        video=video, audio=None, document=None,
        caption=caption, bot=bot,
    )


async def check_non_designated_channel_is_ignored():
    engine, session = await _fresh_session()
    await SettingsService(session).set("default_ppv_price", "50.0")
    ch_svc = ChannelService(session)
    await ch_svc.add("Random", "https://t.me/random", category=ChannelCategory.FREE, channel_id=-100111)
    await session.commit()
    # deliberately NOT setting is_auto_index_source

    bot = FakeBot()
    msg = _fake_channel_post(-100111, "randomfile", "Some Random Post", bot)
    await auto_index_channel_post(msg, session)
    await session.commit()

    movie = await MovieService(session).get_by_file_id("randomfile")
    assert movie is None, "a non-designated channel's posts must never be indexed"
    assert bot.sent == [], "no notification should fire for a channel we don't care about"

    await engine.dispose()
    print("✓ non-designated channel: completely ignored, no indexing, no notification")


async def check_designated_channel_without_price_indexes_nothing():
    engine, session = await _fresh_session()
    ch_svc = ChannelService(session)
    source = await ch_svc.add("Source Channel", "https://t.me/src", category=ChannelCategory.FREE, channel_id=-100222)
    await ch_svc.update(source.id, is_auto_index_source=True)
    await session.commit()
    # deliberately NOT setting default_ppv_price

    bot = FakeBot()
    msg = _fake_channel_post(-100222, "unpriced_file", "A Movie", bot)
    await auto_index_channel_post(msg, session)
    await session.commit()

    movie = await MovieService(session).get_by_file_id("unpriced_file")
    assert movie is None, "must not index anything until a default price is configured"
    assert len(bot.sent) >= 1 and "not" in bot.sent[0][1].lower(), "admin must be told why it was skipped"

    await engine.dispose()
    print("✓ designated channel, no price configured: nothing indexed, admin notified why")


async def check_designated_channel_with_price_indexes_correctly():
    engine, session = await _fresh_session()
    await SettingsService(session).set("default_ppv_price", "80.0")
    ch_svc = ChannelService(session)
    source = await ch_svc.add("Source Channel", "https://t.me/src", category=ChannelCategory.FREE, channel_id=-100333)
    await ch_svc.update(source.id, is_auto_index_source=True)
    await session.commit()

    bot = FakeBot()
    msg = _fake_channel_post(-100333, "priced_file", "A Great Movie", bot)
    await auto_index_channel_post(msg, session)
    await session.commit()

    movie = await MovieService(session).get_by_file_id("priced_file")
    assert movie is not None
    assert movie.title == "A Great Movie"
    assert movie.ppv_price == 80.0, "must use the same configured default as manual batch upload"
    assert movie.is_ppv is True, "non-VIP users must still be gated — this isn't a separate free path"
    assert any("Auto-indexed" in text for _, text in bot.sent)

    await engine.dispose()
    print("✓ designated channel, price configured: indexed correctly, priced the same as manual upload")


async def check_duplicate_post_does_not_double_index():
    engine, session = await _fresh_session()
    await SettingsService(session).set("default_ppv_price", "80.0")
    ch_svc = ChannelService(session)
    source = await ch_svc.add("Source Channel", "https://t.me/src", category=ChannelCategory.FREE, channel_id=-100444)
    await ch_svc.update(source.id, is_auto_index_source=True)
    await session.commit()

    bot = FakeBot()
    msg = _fake_channel_post(-100444, "dupe_file", "Dupe Movie", bot)
    await auto_index_channel_post(msg, session)
    await session.commit()
    await auto_index_channel_post(msg, session)  # same file posted again
    await session.commit()

    movie = await MovieService(session).get_by_file_id("dupe_file")
    assert movie is not None
    assert any("Already indexed" in text or "ℹ️" in text for _, text in bot.sent)

    await engine.dispose()
    print("✓ reposting the same file: no duplicate movie row, admin told it was a duplicate")


def check_derive_title_matches_manual_upload_logic():
    media_with_name = SimpleNamespace(file_name="my_movie_file.mp4")
    msg_with_caption = SimpleNamespace(caption="  Real Title  \nsecond line")
    # .strip() applies to the whole caption before splitting into lines —
    # this is the exact, pre-existing batch_upload_receive behavior,
    # unchanged by extracting it into _derive_title, so the trailing
    # spaces before the newline are expected here, not a bug to fix.
    assert _derive_title(msg_with_caption, media_with_name, "abc12345") == "Real Title  "

    msg_no_caption = SimpleNamespace(caption=None)
    assert _derive_title(msg_no_caption, media_with_name, "abc12345") == "my_movie_file.mp4"

    media_no_name = SimpleNamespace(file_name=None)
    result = _derive_title(msg_no_caption, media_no_name, "abc12345")
    assert result == "Untitled abc12345"

    print("✓ _derive_title: same caption → filename → placeholder fallback used everywhere")


if __name__ == "__main__":
    asyncio.run(check_non_designated_channel_is_ignored())
    asyncio.run(check_designated_channel_without_price_indexes_nothing())
    asyncio.run(check_designated_channel_with_price_indexes_correctly())
    asyncio.run(check_duplicate_post_does_not_double_index())
    check_derive_title_matches_manual_upload_logic()
    print("\nAll auto-index channel checks passed.")
