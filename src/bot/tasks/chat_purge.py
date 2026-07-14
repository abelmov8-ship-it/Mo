"""
Chat purge task — auto-deletes search result messages based on the
DELETE_TIMER_MINUTES setting. Message IDs to clean up would be stored
in a cache (Redis / in-memory dict) keyed by chat_id → [message_id].
This module provides the purge runner.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import NamedTuple

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from bot.config import settings

logger = logging.getLogger(__name__)


class PendingDelete(NamedTuple):
    chat_id: int
    message_id: int
    delete_after: datetime


# In-memory registry — in production use Redis with TTL
_pending: list[PendingDelete] = []


def schedule_delete(chat_id: int, message_id: int) -> None:
    """Called from handlers after sending a search-result message."""
    minutes = settings.DELETE_TIMER_MINUTES
    if minutes == 0:
        return
    delete_at = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    _pending.append(PendingDelete(chat_id, message_id, delete_at))


async def run_chat_purge(bot: Bot) -> None:
    """Deletes all messages whose scheduled delete time has passed."""
    now = datetime.now(timezone.utc)
    due = [p for p in _pending if p.delete_after <= now]
    remaining = [p for p in _pending if p.delete_after > now]
    _pending.clear()
    _pending.extend(remaining)

    for item in due:
        try:
            await bot.delete_message(item.chat_id, item.message_id)
        except TelegramBadRequest:
            pass  # Already deleted or too old
        except Exception as exc:
            logger.debug("Purge error for msg %d: %s", item.message_id, exc)

    if due:
        logger.debug("Chat purge: deleted %d messages.", len(due))
