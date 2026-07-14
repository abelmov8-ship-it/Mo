"""
Runnable self-check for per-channel PPV pricing.

1. _resolve_movie_price: a channel's own custom_ppv_price wins over the
   global default, including when that custom price is exactly 0.0 (must
   not be confused with "no override" — that's the whole reason the
   column is nullable instead of defaulting to 0).
2. _resolve_origin_channel: only resolves for genuine forwards from a
   channel we have a row for; a non-forward or a forward from an unknown
   channel both resolve to None.
3. batch_upload_receive end-to-end: a file forwarded from a channel with
   its own price gets queued at that price; a file from an unpriced
   channel falls back to the global default if one exists; a file from an
   unpriced channel with no global default either gets rejected outright
   (not silently queued at some invented price).
4. batch_upload_start no longer hard-blocks just because no global
   default is set — that gate moved to a per-file check, since an admin
   whose real channels are all individually priced shouldn't be forced to
   configure an unrelated global fallback they'll never use.

Run directly: `python3 tests/check_channel_custom_pricing.py`
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
from bot.handlers.admin.system import (
    _resolve_movie_price,
    _resolve_origin_channel,
    batch_upload_receive,
    batch_upload_start,
)
from bot.services.channel_service import ChannelService
from bot.services.movie_service import MovieService
from bot.services.settings_service import SettingsService


async def _fresh_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    return engine, Session()


async def check_price_resolution_priority():
    engine, session = await _fresh_session()
    ch_svc = ChannelService(session)

    priced = await ch_svc.add("Multi-part", "https://t.me/multipart", category=ChannelCategory.FREE, channel_id=-1001)
    await ch_svc.update(priced.id, custom_ppv_price=15.0)
    free_override = await ch_svc.add("Freebies", "https://t.me/free", category=ChannelCategory.FREE, channel_id=-1002)
    await ch_svc.update(free_override.id, custom_ppv_price=0.0)
    unpriced = await ch_svc.add("Bundles", "https://t.me/bundles", category=ChannelCategory.FREE, channel_id=-1003)
    await session.commit()

    await SettingsService(session).set("default_ppv_price", "40.0")
    await session.commit()

    assert await _resolve_movie_price(session, priced) == 15.0, "channel's own price must win over global default"
    assert await _resolve_movie_price(session, free_override) == 0.0, \
        "an explicit 0.0 override must be respected, not treated as 'no override'"
    assert await _resolve_movie_price(session, unpriced) == 40.0, "unpriced channel falls back to global default"
    assert await _resolve_movie_price(session, None) == 40.0, "no channel at all also falls back to global default"

    await engine.dispose()
    print("✓ _resolve_movie_price: per-channel price wins, 0.0 override respected, unpriced falls back correctly")


async def check_price_resolution_with_no_global_default():
    engine, session = await _fresh_session()
    ch_svc = ChannelService(session)
    unpriced = await ch_svc.add("Bundles", "https://t.me/bundles", category=ChannelCategory.FREE, channel_id=-1004)
    await session.commit()
    # deliberately no default_ppv_price set at all

    assert await _resolve_movie_price(session, unpriced) is None, \
        "no channel price and no global default must resolve to None, never a made-up number"

    await engine.dispose()
    print("✓ _resolve_movie_price: correctly returns None when nothing is configured anywhere")


async def check_resolve_origin_channel():
    engine, session = await _fresh_session()
    ch_svc = ChannelService(session)
    known = await ch_svc.add("Known", "https://t.me/known", category=ChannelCategory.FREE, channel_id=-2001)
    await session.commit()

    forwarded_known = SimpleNamespace(forward_from_chat=SimpleNamespace(id=-2001))
    resolved = await _resolve_origin_channel(session, forwarded_known)
    assert resolved is not None and resolved.id == known.id

    forwarded_unknown = SimpleNamespace(forward_from_chat=SimpleNamespace(id=-9999))
    assert await _resolve_origin_channel(session, forwarded_unknown) is None

    not_forwarded = SimpleNamespace(forward_from_chat=None)
    assert await _resolve_origin_channel(session, not_forwarded) is None

    await engine.dispose()
    print("✓ _resolve_origin_channel: resolves known forwards, None for unknown/non-forwards")


class _FakeState:
    def __init__(self, data=None):
        self._data = data or {}
    async def get_data(self):
        return self._data
    async def update_data(self, **kw):
        self._data.update(kw)
    async def set_state(self, state):
        self._data["_state"] = state
    async def clear(self):
        self._data = {}


class _RecordingMessage:
    def __init__(self, video=None, caption=None, forward_from_chat=None):
        self.video = video
        self.audio = None
        self.document = None
        self.caption = caption
        self.forward_from_chat = forward_from_chat
        self.sent = []
    async def answer(self, text, **kw):
        self.sent.append(text)


async def check_batch_upload_receive_end_to_end():
    engine, session = await _fresh_session()
    ch_svc = ChannelService(session)
    multipart = await ch_svc.add("Multi-part", "https://t.me/mp", category=ChannelCategory.FREE, channel_id=-3001)
    await ch_svc.update(multipart.id, custom_ppv_price=10.0)
    unpriced = await ch_svc.add("Unpriced", "https://t.me/up", category=ChannelCategory.FREE, channel_id=-3002)
    await session.commit()
    await SettingsService(session).set("default_ppv_price", "50.0")
    await session.commit()

    # File 1: forwarded from the priced "Multi-part" channel.
    state = _FakeState()
    msg1 = _RecordingMessage(video=SimpleNamespace(file_id="f1"), caption="Part 1",
                             forward_from_chat=SimpleNamespace(id=-3001))
    await batch_upload_receive(msg1, session, state)
    batch = (await state.get_data())["batch"]
    assert batch[0]["ppv_price"] == 10.0, "must use the channel's own price"
    assert "Multi-part" in msg1.sent[0]

    # File 2: forwarded from an unpriced channel — falls back to global default.
    msg2 = _RecordingMessage(video=SimpleNamespace(file_id="f2"), caption="Bundle",
                             forward_from_chat=SimpleNamespace(id=-3002))
    await batch_upload_receive(msg2, session, state)
    batch = (await state.get_data())["batch"]
    assert batch[1]["ppv_price"] == 50.0, "unpriced channel must fall back to the global default"

    await engine.dispose()
    print("✓ batch_upload_receive: per-file price resolves correctly (channel-specific, then global)")


async def check_batch_upload_receive_rejects_when_unpriceable():
    engine, session = await _fresh_session()
    ch_svc = ChannelService(session)
    unpriced = await ch_svc.add("Unpriced", "https://t.me/up2", category=ChannelCategory.FREE, channel_id=-4001)
    await session.commit()
    # deliberately no default_ppv_price set

    state = _FakeState()
    msg = _RecordingMessage(video=SimpleNamespace(file_id="f3"), caption="Mystery File",
                            forward_from_chat=SimpleNamespace(id=-4001))
    await batch_upload_receive(msg, session, state)

    data = await state.get_data()
    assert data.get("batch", []) == [], "a file that can't be priced must not be queued at all"
    assert any("Skipped" in text for text in msg.sent), "admin must be told clearly why it was skipped"

    await engine.dispose()
    print("✓ batch_upload_receive: rejects (doesn't queue) a file with no resolvable price")


async def check_batch_start_no_longer_hard_gated():
    engine, session = await _fresh_session()
    # deliberately no default_ppv_price configured anywhere

    class FakeCallback:
        class message:
            @staticmethod
            async def edit_text(text, **kw):
                FakeCallback.last_text = text
        async def answer(self):
            pass

    state = _FakeState()
    await batch_upload_start(FakeCallback(), session, state)
    data = await state.get_data()
    assert data.get("_state") is not None, "must actually start the batch, not block on missing global default"
    assert "Set a default PPV price first" not in FakeCallback.last_text, \
        "the old hard block message must be gone — pricing is now resolved per file"

    await engine.dispose()
    print("✓ batch_upload_start: no longer hard-blocked by a missing global default")


if __name__ == "__main__":
    asyncio.run(check_price_resolution_priority())
    asyncio.run(check_price_resolution_with_no_global_default())
    asyncio.run(check_resolve_origin_channel())
    asyncio.run(check_batch_upload_receive_end_to_end())
    asyncio.run(check_batch_upload_receive_rejects_when_unpriceable())
    asyncio.run(check_batch_start_no_longer_hard_gated())
    print("\nAll channel custom pricing checks passed.")
