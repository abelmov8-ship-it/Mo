from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import settings
from bot.database.session import create_db_and_tables, AsyncSessionFactory
from bot.middlewares.auth import AuthMiddleware
from bot.middlewares.anti_spam import AntiSpamMiddleware
from bot.middlewares.database import DatabaseMiddleware
from bot.middlewares.i18n import I18nMiddleware
from bot.middlewares.maintenance import MaintenanceMiddleware

# ── User routers ──────────────────────────────────────────────────────────────
from bot.handlers.user import (
    start, search, channels, trending,
    vip, payment, wallet, photo_editor,
    profile, referral, support,
)

# ── Admin routers ─────────────────────────────────────────────────────────────
from bot.handlers.admin import (
    panel, broadcast, analytics,
    channels as admin_channels,
    payment as admin_payment,
    system, content, menu as admin_menu, welcome_buttons as admin_welcome_buttons,
    trending_admin, delivery_buttons, faq as admin_faq, texts as admin_texts,
)

from bot.tasks.scheduler import setup_scheduler
from bot.webapp import setup_webhook_server

logger = logging.getLogger(__name__)


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    bot = Bot(
        token=settings.BOT_TOKEN.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    # ── Middlewares (order is: outer → inner) ─────────────────────────────────
    dp.update.outer_middleware(AuthMiddleware())
    dp.update.middleware(DatabaseMiddleware())
    dp.update.middleware(I18nMiddleware())
    dp.update.middleware(MaintenanceMiddleware())
    dp.update.middleware(AntiSpamMiddleware())

    # ── User routers ──────────────────────────────────────────────────────────
    dp.include_router(start.router)
    dp.include_router(channels.router)
    dp.include_router(trending.router)
    dp.include_router(vip.router)
    dp.include_router(payment.router)
    dp.include_router(wallet.router)
    dp.include_router(photo_editor.router)
    dp.include_router(profile.router)
    dp.include_router(referral.router)
    dp.include_router(support.router)

    # ── Admin routers (IsAdmin filter applied inside each router) ─────────────
    dp.include_router(panel.router)
    dp.include_router(broadcast.router)
    dp.include_router(analytics.router)
    dp.include_router(admin_channels.router)
    dp.include_router(admin_payment.router)
    dp.include_router(system.router)
    dp.include_router(content.router)
    dp.include_router(admin_menu.router)
    dp.include_router(admin_welcome_buttons.router)
    dp.include_router(trending_admin.router)
    dp.include_router(delivery_buttons.router)
    dp.include_router(admin_faq.router)
    dp.include_router(admin_texts.router)

    # ponytail: search.router owns a catch-all text handler (any non-command,
    # non-"🔍" text -> treated as a movie query). It must be included dead
    # last so every specific F.text == "<button label>" handler above gets
    # first crack at reply-keyboard taps; otherwise every button press falls
    # through to "no results, request movie" before reaching its real router.
    dp.include_router(search.router)

    # ── Database ──────────────────────────────────────────────────────────────
    await create_db_and_tables()
    logger.info("Database tables verified.")

    from bot.services.settings_service import hydrate_runtime_settings
    async with AsyncSessionFactory() as _session:
        await hydrate_runtime_settings(_session)
    logger.info("Persisted admin settings applied.")

    from bot.utils.i18n import hydrate_bot_texts
    async with AsyncSessionFactory() as _session:
        await hydrate_bot_texts(_session)
    logger.info("Admin-edited bot texts loaded.")

    # ── Background scheduler ──────────────────────────────────────────────────
    scheduler = setup_scheduler(bot)
    scheduler.start()
    logger.info("Scheduler started with %d jobs.", len(scheduler.get_jobs()))

    # ── Chapa webhook server ──────────────────────────────────────────────────
    webhook_runner = await setup_webhook_server(bot)

    try:
        logger.info("Bot is live. Polling for updates…")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown(wait=False)
        await webhook_runner.cleanup()
        await bot.session.close()
        logger.info("Bot stopped cleanly.")


if __name__ == "__main__":
    asyncio.run(main())
