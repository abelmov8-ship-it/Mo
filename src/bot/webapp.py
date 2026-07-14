from __future__ import annotations

import logging

from aiogram import Bot
from aiohttp import web

from bot.config import settings
from bot.database.session import AsyncSessionFactory
from bot.services.chapa_fulfillment import FulfillOutcome, finalize_chapa_payment
from bot.utils.chapa_signature import verify_chapa_signature

logger = logging.getLogger(__name__)


def _extract_tx_ref(payload: dict) -> str | None:
    # Chapa's transaction webhook carries the reference as "tx_ref"; payout
    # and refund event payloads (also delivered to the same URL if an admin
    # subscribes to those event types) don't, and aren't ones we act on.
    return payload.get("tx_ref")


async def chapa_webhook_handler(request: web.Request) -> web.Response:
    if not settings.CHAPA_WEBHOOK_SECRET:
        logger.warning("Chapa webhook received but CHAPA_WEBHOOK_SECRET is not configured.")
        return web.json_response({"error": "webhook not configured"}, status=503)

    raw_body = await request.read()
    secret = settings.CHAPA_WEBHOOK_SECRET.get_secret_value()
    if not verify_chapa_signature(
        secret,
        raw_body,
        request.headers.get("chapa-signature"),
        request.headers.get("x-chapa-signature"),
    ):
        logger.warning("Chapa webhook signature mismatch — discarding request.")
        return web.json_response({"error": "invalid signature"}, status=401)

    try:
        payload = await request.json()
    except ValueError:
        return web.json_response({"error": "bad json"}, status=400)

    tx_ref = _extract_tx_ref(payload)
    if not tx_ref:
        # Correctly-signed but not a transaction event we handle — ack with
        # 200 so Chapa doesn't retry a request we're deliberately ignoring.
        return web.json_response({"status": "ignored"}, status=200)

    async with AsyncSessionFactory() as session:
        outcome, message, telegram_id = await finalize_chapa_payment(session, tx_ref)
        await session.commit()

    # ponytail: only CREDITED notifies the user here — that's the "automatic
    # confirmation without any manual button clicks" this endpoint exists
    # for. ALREADY_DONE/VERIFY_FAILED/NOT_FOUND stay silent to the user: the
    # manual Verify button and the abandoned-payment reminder job are the
    # fallback paths for anything that doesn't resolve cleanly here, so this
    # handler doesn't need to be the one place every edge case gets surfaced.
    if outcome == FulfillOutcome.CREDITED and telegram_id:
        bot: Bot = request.app["bot"]
        try:
            await bot.send_message(telegram_id, message)
        except Exception:
            logger.warning("Chapa webhook: credited tx_ref=%s but couldn't message user %s", tx_ref, telegram_id)

    # ponytail: always 200 once the signature checks out and the JSON parses
    # — even for VERIFY_FAILED — rather than returning non-2xx to trigger
    # Chapa's own retry policy. Ceiling: if Chapa's verify endpoint is ever
    # meaningfully behind its own webhook delivery, this leans on the
    # abandoned-payment reminder job / manual Verify tap to close the gap
    # instead of a webhook retry. Upgrade path is returning 202/5xx for
    # VERIFY_FAILED specifically, if that ever proves necessary in practice.
    return web.json_response({"status": outcome.value}, status=200)


async def setup_webhook_server(bot: Bot) -> web.AppRunner:
    """Starts a tiny HTTP server alongside the polling bot, purely to
    receive the Chapa webhook. Telegram updates still arrive via long
    polling — this is a separate, unrelated listener Chapa's servers call
    into directly."""
    app = web.Application()
    app["bot"] = bot
    app.router.add_post("/webhooks/chapa", chapa_webhook_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", settings.WEBHOOK_PORT)
    await site.start()
    logger.info("Webhook server listening on 0.0.0.0:%d (/webhooks/chapa).", settings.WEBHOOK_PORT)
    return runner
