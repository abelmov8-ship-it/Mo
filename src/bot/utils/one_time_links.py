"""
One-time invite link generator.

For each channel access request we create a new, single-use invite link via the
Telegram Bot API (create_chat_invite_link with member_limit=1). The link is
returned to the user and automatically expires after they use it once.

If the bot lacks the required admin permissions in the channel, the error is
caught gracefully and the public channel URL is returned as a fallback.
"""
from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

from bot.database.models.channel import Channel

logger = logging.getLogger(__name__)


async def generate_one_time_link(bot: Bot, channel: Channel) -> str:
    """
    Creates a one-time Telegram invite link for *channel*.
    Falls back to the channel's stored URL if the bot lacks permission.
    """
    if channel.channel_id is None:
        return channel.url

    try:
        link = await bot.create_chat_invite_link(
            chat_id=channel.channel_id,
            member_limit=1,
            name="OTL",
        )
        return link.invite_link
    except (TelegramForbiddenError, TelegramBadRequest) as exc:
        logger.warning(
            "Could not create one-time link for channel %d: %s", channel.channel_id, exc
        )
        return channel.url
