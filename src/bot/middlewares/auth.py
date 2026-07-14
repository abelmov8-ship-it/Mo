from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from bot.config import settings


class AuthMiddleware(BaseMiddleware):
    """
    Attaches ``data["is_admin"]`` to every update so handlers don't need to
    re-check the config list themselves.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = None
        if isinstance(event, Update):
            if event.message:
                tg_user = event.message.from_user
            elif event.callback_query:
                tg_user = event.callback_query.from_user

        data["is_admin"] = tg_user is not None and tg_user.id in settings.ADMIN_IDS
        return await handler(event, data)
