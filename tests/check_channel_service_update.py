"""
Regression check for ChannelService.update() — its identifier parameter
used to be named `channel_id`, which collided with the model's own
`channel_id` field the instant a caller needed to set it via kwargs:
    update(row_id, channel_id=new_value)
raised `TypeError: got multiple values for argument 'channel_id'` every
time (two call sites in handlers/admin/channels.py hit this in
production). Renamed the identifier param to `id` so a `channel_id` kwarg
can pass through without colliding with it.

Run directly: `python3 tests/check_channel_service_update.py`
(Needs sqlalchemy + aiosqlite installed — same as every other DB-touching
check script in this suite.)
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from bot.database.base import Base
import bot.database.models  # noqa: F401  registers all models on Base.metadata
from bot.database.models.channel import ChannelCategory
from bot.services.channel_service import ChannelService


def check(label: str, condition: bool) -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        raise SystemExit(1)


async def main() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as session:
        ch = await ChannelService(session).add(
            name="Test Channel", url="https://t.me/test", category=ChannelCategory.FREE
        )
        await session.commit()
        channel_row_id = ch.id

        # This exact call shape (positional row id + a channel_id= kwarg)
        # is precisely what crashed before the fix.
        ok = await ChannelService(session).update(channel_row_id, channel_id=-100123456789)
        check("update() accepts a channel_id= kwarg without colliding with the identifier param", ok is True)
        await session.commit()

    async with Session() as session:
        fresh = await ChannelService(session).get_by_id(channel_row_id)
        check("channel_id field was actually persisted", fresh.channel_id == -100123456789)

        ok_name = await ChannelService(session).update(channel_row_id, name="Renamed")
        check("updating an unrelated field (name) still works", ok_name is True)

        missing = await ChannelService(session).update(999999, name="ghost")
        check("update() on a nonexistent id returns False, not an error", missing is False)

    await engine.dispose()
    print("\nAll ChannelService.update checks passed.")


asyncio.run(main())
