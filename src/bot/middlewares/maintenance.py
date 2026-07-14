from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject, Update

from bot.config import settings


class MaintenanceMiddleware(BaseMiddleware):
    """
    When MAINTENANCE_MODE is True, every non-admin update is dropped and the
    user receives a polite maintenance notice. Admin IDs bypass this gate.

    channel_post updates always bypass this gate entirely, regardless of
    MAINTENANCE_MODE — there's no user to notify (channel posts aren't
    "from" anyone the way messages/callbacks are), and pausing user-facing
    commands has no relationship to whether channel auto-indexing should
    keep running. Before this fix, a channel_post update fell through
    every branch below (none of them check event.channel_post) and hit
    the final `return None`, silently killing every handler downstream —
    including auto-indexing — with no error logged, any time maintenance
    mode was on.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Update) and event.channel_post:
            return await handler(event, data)

        if not settings.MAINTENANCE_MODE:
            return await handler(event, data)

        tg_user = None
        if isinstance(event, Update):
            if event.message:
                tg_user = event.message.from_user
            elif event.callback_query:
                tg_user = event.callback_query.from_user

        if tg_user and tg_user.id in settings.ADMIN_IDS:
            return await handler(event, data)

        # Notify the blocked user
        if isinstance(event, Update):
            if event.message:
                await event.message.answer(
                    "🛠 The bot is currently under maintenance. Please try again shortly."
                )
            elif event.callback_query:
                await event.callback_query.answer(
                    "🛠 Maintenance in progress.", show_alert=True
                )
        return None
