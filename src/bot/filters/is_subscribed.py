from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery
from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from bot.database.models.channel import Channel


async def get_missing_channels(bot: Bot, session: AsyncSession, telegram_id: int) -> list[Channel]:
    """Returns the force-join channels `telegram_id` has not joined (empty = all good)."""
    result = await session.execute(
        select(Channel).where(Channel.force_join.is_(True))
    )
    force_channels: list[Channel] = list(result.scalars().all())
    if not force_channels:
        return []

    missing: list[Channel] = []
    for channel in force_channels:
        if channel.channel_id is None:
            continue
        try:
            member = await bot.get_chat_member(channel.channel_id, telegram_id)
            if member.status in ("left", "kicked", "banned"):
                missing.append(channel)
        except (TelegramForbiddenError, TelegramBadRequest):
            # Bot lacks permission — skip gracefully
            pass
    return missing


class IsSubscribed(BaseFilter):
    """
    Passes only if the user is a member of every channel that has force_join=True.

    ponytail: a plain bool, deliberately. Returning the missing-channel list
    as filter data looked convenient, but a non-empty dict is truthy in
    Python — the old version returned `{"not_subscribed": [...]}` on a
    *blocked* user, which is truthy, so the filter always passed. Handlers
    that need the actual list call get_missing_channels() themselves.
    """

    async def __call__(
        self,
        event: Message | CallbackQuery,
        bot: Bot,
        session: AsyncSession,
    ) -> bool:
        tg_user = event.from_user
        if tg_user is None:
            return False
        missing = await get_missing_channels(bot, session, tg_user.id)
        return not missing
