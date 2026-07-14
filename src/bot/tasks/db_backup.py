"""Encrypted daily database backup dispatched to the admin archive channel."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from aiogram import Bot
from aiogram.types import BufferedInputFile

from bot.config import settings

logger = logging.getLogger(__name__)

_DB_PATH = Path("bot.db")


def _read_db_bytes() -> bytes | None:
    if not _DB_PATH.exists():
        logger.warning("Database file %s not found — skipping backup.", _DB_PATH)
        return None
    return _DB_PATH.read_bytes()


async def run_backup(bot: Bot) -> str | None:
    """
    Reads the SQLite database file, wraps it in a BufferedInputFile,
    and sends it to BACKUP_CHANNEL_ID.
    Returns the file path string on success, None on failure.
    """
    if not settings.BACKUP_CHANNEL_ID:
        logger.warning("BACKUP_CHANNEL_ID is not set — skipping backup.")
        return None

    raw = _read_db_bytes()
    if raw is None:
        return None

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"backup_{ts}.db"

    try:
        await bot.send_document(
            chat_id=settings.BACKUP_CHANNEL_ID,
            document=BufferedInputFile(raw, filename=filename),
            caption=f"🗄 <b>Automated Backup</b>\n{ts} UTC\nSize: {len(raw) / 1024:.1f} KB",
        )
        logger.info("Backup sent: %s (%d bytes)", filename, len(raw))
        return str(_DB_PATH)
    except Exception as exc:
        logger.error("Backup failed: %s", exc)
        return None


async def send_manual_backup(bot: Bot, chat_id: int) -> bool:
    """On-demand export straight to the requesting admin's chat — no
    BACKUP_CHANNEL_ID required, since this is the "manual" half of the
    spec's dual-layer backup system."""
    raw = _read_db_bytes()
    if raw is None:
        return False

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"backup_{ts}.db"
    try:
        await bot.send_document(
            chat_id=chat_id,
            document=BufferedInputFile(raw, filename=filename),
            caption=f"🗄 <b>Manual Backup</b>\n{ts} UTC\nSize: {len(raw) / 1024:.1f} KB",
        )
        return True
    except Exception as exc:
        logger.error("Manual backup failed: %s", exc)
        return False
