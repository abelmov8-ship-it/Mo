from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models.user import User, UserLanguage


class I18nMiddleware(BaseMiddleware):
    """
    Looks up the user's saved language preference and stores it in
    ``data["locale"]`` so handlers can pass it to translation helpers.
    Defaults to English if the user is not yet in the DB or has no preference.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        locale = UserLanguage.EN  # safe default

        tg_user = None
        if isinstance(event, Update):
            tg_user = (
                event.message.from_user if event.message
                else event.callback_query.from_user if event.callback_query
                else None
            )

        session: AsyncSession | None = data.get("session")
        if tg_user and session:
            result = await session.execute(
                select(User.language).where(User.telegram_id == tg_user.id)
            )
            row = result.scalar_one_or_none()
            if row is not None:
                locale = row

        data["locale"] = locale
        return await handler(event, data)
