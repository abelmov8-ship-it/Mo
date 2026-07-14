"""Nudges users who started a Chapa checkout but never completed it."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from sqlalchemy import select

from bot.database.models.payment import Payment, PaymentGateway, PaymentStatus
from bot.database.models.user import User
from bot.database.session import AsyncSessionFactory
from bot.utils.i18n import t

logger = logging.getLogger(__name__)

# ponytail: fixed cutoff rather than an admin-configurable setting — "a few
# minutes" (the actual ask) doesn't need a tunable knob yet. If this ever
# needs to vary by plan/amount, that's the upgrade path, not a reason to
# add a settings-table round trip now.
ABANDONED_CUTOFF_MINUTES = 15


def _is_abandoned(created_at: datetime, now: datetime, cutoff_minutes: int = ABANDONED_CUTOFF_MINUTES) -> bool:
    """Pure predicate so the cutoff math is checkable without a DB — see
    tests/check_abandoned_payment.py. The SQL query below re-expresses this
    same rule as a `created_at <= cutoff` filter (so the index actually
    narrows the scan); keep both in sync if the rule ever changes."""
    return now - created_at >= timedelta(minutes=cutoff_minutes)


async def run_abandoned_payment_reminder(bot: Bot) -> None:
    async with AsyncSessionFactory() as session:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=ABANDONED_CUTOFF_MINUTES)

        result = await session.execute(
            select(Payment, User)
            .join(User, User.id == Payment.user_id)
            .where(Payment.gateway == PaymentGateway.CHAPA)
            .where(Payment.status == PaymentStatus.PENDING)
            .where(Payment.reminder_sent_at.is_(None))
            .where(Payment.created_at <= cutoff)
        )
        pairs = list(result.all())

        reminded = 0
        for payment, user in pairs:
            try:
                await bot.send_message(
                    user.telegram_id,
                    t("reminder.abandoned_payment", user.language, amount=f"{payment.amount:.0f}"),
                )
                payment.reminder_sent_at = now
                reminded += 1
            except Exception as exc:
                logger.warning("Could not remind user %d about tx_ref=%s: %s", user.telegram_id, payment.reference, exc)

        if reminded:
            await session.commit()
            logger.info("Abandoned-payment recovery: reminded %d users.", reminded)
