from __future__ import annotations

import logging

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    """
    Registers all background cron jobs and returns the configured scheduler.
    Call scheduler.start() after this function in main.py.
    """
    from bot.tasks.auto_kick import run_auto_kick
    from bot.tasks.reminders import run_reminders
    from bot.tasks.db_backup import run_backup
    from bot.tasks.chat_purge import run_chat_purge
    from bot.tasks.content_scheduler import run_content_scheduler
    from bot.tasks.abandoned_payment import run_abandoned_payment_reminder

    scheduler = AsyncIOScheduler(timezone="UTC")

    # Auto-kick expired VIP users — every hour
    scheduler.add_job(
        run_auto_kick,
        trigger=IntervalTrigger(hours=1),
        args=[bot],
        id="auto_kick",
        name="Auto-kick expired VIP",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # Expiry reminder alerts (3-day and 1-day) — daily at 08:00 UTC
    scheduler.add_job(
        run_reminders,
        trigger=CronTrigger(hour=8, minute=0),
        args=[bot],
        id="expiry_reminders",
        name="VIP expiry reminders",
        replace_existing=True,
    )

    # Encrypted DB backup — daily at 03:00 UTC
    scheduler.add_job(
        run_backup,
        trigger=CronTrigger(hour=3, minute=0),
        args=[bot],
        id="db_backup",
        name="Daily DB backup",
        replace_existing=True,
    )

    # Auto-delete search-result messages once their delete timer elapses —
    # checked every 30s so a 1-minute timer still feels prompt.
    scheduler.add_job(
        run_chat_purge,
        trigger=IntervalTrigger(seconds=30),
        args=[bot],
        id="chat_purge",
        name="Chat history auto-purge",
        replace_existing=True,
    )

    # Fire queued admin posts whose scheduled time has arrived.
    scheduler.add_job(
        run_content_scheduler,
        trigger=IntervalTrigger(seconds=30),
        args=[bot],
        id="content_scheduler",
        name="Scheduled channel posts",
        replace_existing=True,
    )

    # Nudge users who started a Chapa checkout but never finished it.
    scheduler.add_job(
        run_abandoned_payment_reminder,
        trigger=IntervalTrigger(minutes=5),
        args=[bot],
        id="abandoned_payment_reminder",
        name="Abandoned Chapa payment recovery",
        replace_existing=True,
        misfire_grace_time=300,
    )

    logger.info("Registered %d scheduler jobs.", len(scheduler.get_jobs()))
    return scheduler
