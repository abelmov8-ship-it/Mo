from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject, Update

from bot.config import settings


class AntiSpamMiddleware(BaseMiddleware):
    """
    Sliding-window rate limiter. If a user fires more than
    ANTI_SPAM_THRESHOLD updates per second they receive a single
    cool-down notice and are ignored for ANTI_SPAM_LOCKOUT_SECONDS.
    """

    def __init__(self) -> None:
        # telegram_id → deque of Unix timestamps of recent updates
        self._window: dict[int, deque[float]] = defaultdict(deque)
        # telegram_id → Unix timestamp when lockout expires
        self._locked: dict[int, float] = {}

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

        if tg_user is None:
            return await handler(event, data)

        uid = tg_user.id
        now = time.monotonic()
        threshold = settings.ANTI_SPAM_THRESHOLD
        lockout = settings.ANTI_SPAM_LOCKOUT_SECONDS

        # Check if currently locked
        if uid in self._locked:
            if now < self._locked[uid]:
                return None   # silently drop
            else:
                del self._locked[uid]

        # Slide the window to the last 1 second
        window = self._window[uid]
        while window and now - window[0] > 1.0:
            window.popleft()

        window.append(now)

        if len(window) > threshold:
            self._locked[uid] = now + lockout
            self._window[uid].clear()
            # Notify the user once
            if isinstance(event, Update) and event.message:
                await event.message.answer(
                    f"⚠️ Too many requests. Please wait {lockout} seconds."
                )
            return None

        return await handler(event, data)
