"""Auto-kick expired VIP users from premium channels."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

from bot.database.models.user import User
from bot.database.models.channel import Channel, ChannelCategory
from bot.database.session import AsyncSessionFactory
from bot.services.user_service import UserService
from bot.services.channel_service import ChannelService
from bot.utils.i18n import t

logger = logging.getLogger(__name__)


async def run_auto_kick(bot: Bot) -> None:
    """
    Checks all users whose VIP has expired, revokes their flag,
    kicks them from VIP channels, and sends a renewal notification.
    """
    async with AsyncSessionFactory() as session:
        from sqlalchemy import select
        from bot.database.models.subscription import Subscription

        now = datetime.now(timezone.utc)

        # Find users flagged as VIP but with no active subscription
        expired_result = await session.execute(
            select(User)
            .where(User.is_vip.is_(True))
            .where(
                ~User.id.in_(
                    select(Subscription.user_id)
                    .where(Subscription.expires_at > now)
                )
            )
        )
        expired_users: list[User] = list(expired_result.scalars().all())

        ch_svc = ChannelService(session)
        vip_channels = await ch_svc.get_by_category(ChannelCategory.VIP)

        for user in expired_users:
            user.is_vip = False

            # Kick from all VIP channels
            for ch in vip_channels:
                if ch.channel_id is None:
                    continue
                try:
                    await bot.ban_chat_member(ch.channel_id, user.telegram_id)
                    await bot.unban_chat_member(ch.channel_id, user.telegram_id)
                except (TelegramForbiddenError, TelegramBadRequest):
                    pass

            # Notify user
            try:
                await bot.send_message(user.telegram_id, t("vip.expired", user.language))
            except Exception:
                pass

        await session.commit()
        if expired_users:
            logger.info("Auto-kick: revoked VIP from %d users.", len(expired_users))
