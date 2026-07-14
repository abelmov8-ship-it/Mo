from datetime import datetime, timezone

from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from bot.database.models.subscription import Subscription
from bot.database.models.user import User


class IsVip(BaseFilter):
    """Passes if the user has an active, non-expired VIP subscription."""

    async def __call__(
        self, event: Message | CallbackQuery, session: AsyncSession
    ) -> bool:
        tg_user = event.from_user
        if tg_user is None:
            return False

        now = datetime.now(timezone.utc)

        result = await session.execute(
            select(Subscription)
            .join(User, User.id == Subscription.user_id)
            .where(User.telegram_id == tg_user.id)
            .where(Subscription.expires_at > now)
            .limit(1)
        )
        return result.scalar_one_or_none() is not None
