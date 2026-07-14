"""Content scheduler — fires queued admin posts at their scheduled time."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from aiogram import Bot

logger = logging.getLogger(__name__)

# ponytail: plain in-process list, not a DB table or persistent queue.
# Fine for this bot's single-process polling deployment (matches how
# MAINTENANCE_MODE etc. also live in-process), but scheduled posts are
# lost on restart/redeploy and this won't work if ever run as multiple
# worker processes. Upgrade path: a `scheduled_posts` table (same shape as
# the Setting/SearchLog tables added elsewhere) if losing a queued post to
# a redeploy ever actually happens.
_queue: list[dict] = []


def queue_post(
    channel_id: int,
    text: str,
    fire_at: datetime,
    photo_id: str | None = None,
    video_id: str | None = None,
    markup=None,
) -> None:
    _queue.append(
        dict(channel_id=channel_id, text=text, photo_id=photo_id,
             video_id=video_id, markup=markup, fire_at=fire_at)
    )
    logger.info("Queued post to channel %d at %s", channel_id, fire_at)


async def run_content_scheduler(bot: Bot) -> None:
    """Fires all posts whose scheduled time has arrived."""
    now = datetime.now(timezone.utc)
    due = [p for p in _queue if p["fire_at"] <= now]
    remaining = [p for p in _queue if p["fire_at"] > now]
    _queue.clear()
    _queue.extend(remaining)

    for post in due:
        try:
            if post["photo_id"]:
                await bot.send_photo(post["channel_id"], photo=post["photo_id"],
                                     caption=post["text"], reply_markup=post["markup"])
            elif post["video_id"]:
                await bot.send_video(post["channel_id"], video=post["video_id"],
                                     caption=post["text"], reply_markup=post["markup"])
            else:
                await bot.send_message(post["channel_id"], post["text"],
                                       reply_markup=post["markup"])
            logger.info("Scheduled post fired to channel %d.", post["channel_id"])
        except Exception as exc:
            logger.error("Scheduled post failed: %s", exc)
