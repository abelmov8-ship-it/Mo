"""Grace-period renewal reminders — 3 days and 1 day before VIP expires."""
from __future__ import annotations

import logging

from aiogram import Bot

from bot.database.session import AsyncSessionFactory
from bot.services.user_service import UserService
from bot.utils.formatters import format_expiry
from bot.utils.i18n import t

logger = logging.getLogger(__name__)


async def run_reminders(bot: Bot) -> None:
    async with AsyncSessionFactory() as session:
        user_svc = UserService(session)

        for days_before in (3, 1):
            pairs = await user_svc.get_expiring_soon(within_days=days_before)

            for user, sub in pairs:
                try:
                    await bot.send_message(
                        user.telegram_id,
                        t(
                            "reminder.expiry", user.language,
                            days=days_before, suffix="" if days_before == 1 else "s",
                            expiry=format_expiry(sub, user.language),
                        ),
                    )
                    logger.debug("Sent %d-day reminder to user %d.", days_before, user.telegram_id)
                except Exception as exc:
                    logger.warning("Could not remind user %d: %s", user.telegram_id, exc)
