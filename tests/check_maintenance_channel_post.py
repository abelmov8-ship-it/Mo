"""
Runnable self-check for why auto-indexing appeared to do nothing.

Two independent, real gaps, either of which alone fully explains "I posted
a file and nothing showed up in search, with no visible error":

1. MaintenanceMiddleware had no branch for channel_post updates, so it
   fell through to `return None` whenever MAINTENANCE_MODE was True —
   silently killing every handler downstream, auto-indexing included,
   with nothing logged. channel_post must always bypass this gate: there's
   no user to notify, and pausing user commands has no relationship to
   whether channel indexing should keep running.
2. Channel.channel_id is nullable, and the channel creation wizard treats
   setting it as a separate step from naming/URL — so a channel could be
   flagged as an Auto-Index Source while its channel_id is still unset,
   in which case no real incoming channel_post could ever match it.
   toggle_auto_index_source now refuses to turn the flag on in that state
   and says why, instead of silently succeeding while being non-functional.

Run directly: `python3 tests/check_maintenance_channel_post.py`
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
from bot.handlers.admin.channels import toggle_auto_index_source
from bot.middlewares.maintenance import MaintenanceMiddleware
from bot.services.channel_service import ChannelService


async def _fresh_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    return engine, Session()


async def check_channel_post_bypasses_maintenance_mode():
    from bot import config
    config.settings.MAINTENANCE_MODE = True

    mw = MaintenanceMiddleware()
    handler_called = {"value": False}

    async def fake_handler(event, data):
        handler_called["value"] = True
        return "ok"

    fake_update = SimpleNamespace(message=None, callback_query=None, channel_post=SimpleNamespace())
    # Must look like an aiogram Update to the isinstance() check inside the
    # middleware — patch the class check by using the real Update where
    # possible; simplest robust check here is via the actual aiogram type.
    from aiogram.types import Update
    real_update = Update.model_construct(update_id=1, channel_post=SimpleNamespace(), message=None, callback_query=None)

    result = await mw(fake_handler, real_update, {})
    assert handler_called["value"] is True, "channel_post must reach the handler even when MAINTENANCE_MODE is True"
    assert result == "ok"

    config.settings.MAINTENANCE_MODE = False
    print("✓ MaintenanceMiddleware: channel_post always bypasses the maintenance gate")


async def check_message_still_blocked_during_maintenance():
    from bot import config
    config.settings.MAINTENANCE_MODE = True
    config.settings.ADMIN_IDS = [999]  # this user is NOT in the list

    mw = MaintenanceMiddleware()
    handler_called = {"value": False}

    async def fake_handler(event, data):
        handler_called["value"] = True
        return "ok"

    from aiogram.types import Update, Message, Chat, User as TgUser
    fake_message = SimpleNamespace(
        from_user=SimpleNamespace(id=111, is_bot=False),
        answer=lambda *a, **kw: asyncio.sleep(0),
    )
    real_update = Update.model_construct(update_id=2, message=fake_message, callback_query=None, channel_post=None)

    await mw(fake_handler, real_update, {})
    assert handler_called["value"] is False, "regular user messages must still be blocked during maintenance — unchanged behaviour"

    config.settings.MAINTENANCE_MODE = False
    print("✓ MaintenanceMiddleware: ordinary (non-admin) messages are still correctly blocked during maintenance")


async def check_toggle_refuses_without_channel_id():
    engine, session = await _fresh_session()
    ch_svc = ChannelService(session)
    no_id_channel = await ch_svc.add("No ID Channel", "https://t.me/noid", category=ChannelCategory.FREE)
    await session.commit()
    assert no_id_channel.channel_id is None

    alerts = []
    class FakeCallback:
        data = f"ch:toggle_autoindex:{no_id_channel.id}"
        class message:
            pass
        async def answer(self, text, show_alert=False):
            alerts.append(text)

    await toggle_auto_index_source(FakeCallback(), session)
    await session.commit()

    refetched = await ch_svc.get_by_id(no_id_channel.id)
    assert refetched.is_auto_index_source is False, "must not silently turn on for a channel with no channel_id"
    assert any("Channel ID" in text for text in alerts), "admin must be told exactly why it was refused"

    await engine.dispose()
    print("✓ toggle_auto_index_source: refuses to enable without a channel_id set, and says why")


async def check_toggle_succeeds_with_channel_id():
    engine, session = await _fresh_session()
    ch_svc = ChannelService(session)
    ok_channel = await ch_svc.add("OK Channel", "https://t.me/ok", category=ChannelCategory.FREE, channel_id=-100999)
    await session.commit()

    class FakeCallback:
        data = f"ch:toggle_autoindex:{ok_channel.id}"
        async def answer(self, text, show_alert=False):
            pass

    await toggle_auto_index_source(FakeCallback(), session)
    await session.commit()

    refetched = await ch_svc.get_by_id(ok_channel.id)
    assert refetched.is_auto_index_source is True, "must succeed normally when channel_id is set"

    await engine.dispose()
    print("✓ toggle_auto_index_source: works normally once channel_id is set")


if __name__ == "__main__":
    asyncio.run(check_channel_post_bypasses_maintenance_mode())
    asyncio.run(check_message_still_blocked_during_maintenance())
    asyncio.run(check_toggle_refuses_without_channel_id())
    asyncio.run(check_toggle_succeeds_with_channel_id())
    print("\nAll checks passed.")
