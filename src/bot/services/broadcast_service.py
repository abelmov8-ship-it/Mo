from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import InlineKeyboardMarkup

from bot.database.models.user import User

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 25        # users per batch
_INTER_CHUNK_DELAY = 1  # seconds between batches to stay within Telegram rate limits


@dataclass
class BroadcastResult:
    sent: int = 0
    failed: int = 0
    blocked: int = 0
    errors: list[str] = field(default_factory=list)


class BroadcastService:
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def send_to_users(
        self,
        users: list[User],
        text: str,
        photo_file_id: str | None = None,
        video_file_id: str | None = None,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> BroadcastResult:
        """
        Sends a message to each user in *users* in batches.
        Handles FloodWait and blocked-bot errors gracefully.
        """
        result = BroadcastResult()

        for i in range(0, len(users), _CHUNK_SIZE):
            chunk = users[i : i + _CHUNK_SIZE]
            await asyncio.gather(
                *[
                    self._send_one(user, text, photo_file_id, video_file_id, reply_markup, result)
                    for user in chunk
                ],
                return_exceptions=True,
            )
            await asyncio.sleep(_INTER_CHUNK_DELAY)

        logger.info(
            "Broadcast complete: sent=%d failed=%d blocked=%d",
            result.sent, result.failed, result.blocked,
        )
        return result

    async def _send_one(
        self,
        user: User,
        text: str,
        photo_file_id: str | None,
        video_file_id: str | None,
        reply_markup: InlineKeyboardMarkup | None,
        result: BroadcastResult,
    ) -> None:
        try:
            if photo_file_id:
                await self.bot.send_photo(
                    chat_id=user.telegram_id,
                    photo=photo_file_id,
                    caption=text,
                    reply_markup=reply_markup,
                )
            elif video_file_id:
                await self.bot.send_video(
                    chat_id=user.telegram_id,
                    video=video_file_id,
                    caption=text,
                    reply_markup=reply_markup,
                )
            else:
                await self.bot.send_message(
                    chat_id=user.telegram_id,
                    text=text,
                    reply_markup=reply_markup,
                )
            result.sent += 1
        except TelegramForbiddenError:
            result.blocked += 1
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after + 1)
            result.failed += 1
        except Exception as exc:
            result.failed += 1
            result.errors.append(f"{user.telegram_id}: {exc}")
