from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database.models.menu_button import MenuButtonAction
from bot.database.models.search_log import SearchLog, SearchLogKind
from bot.database.models.user import UserLanguage
from bot.filters.is_subscribed import IsSubscribed, get_missing_channels
from bot.filters.menu_action import MenuAction
from bot.keyboards.user.search import force_join_keyboard
from bot.services.movie_service import MovieService
from bot.services.user_service import UserService
from bot.services.watchlist_service import WatchlistService
from bot.tasks.chat_purge import schedule_delete
from bot.utils.i18n import t
from bot.utils.movie_delivery import build_delivered_movie_keyboard, build_zero_result_keyboard, send_movie_or_ppv_gate

router = Router(name="user:search")
logger = logging.getLogger(__name__)


@router.message(MenuAction(MenuButtonAction.SEARCH))
async def prompt_search(
    message: Message,
    bot: Bot,
    session: AsyncSession,
    state: FSMContext,
    locale: UserLanguage = UserLanguage.EN,
) -> None:
    """The dedicated entry point — this is what's meant to trigger the force-join gate."""
    await state.clear()
    missing = await get_missing_channels(bot, session, message.from_user.id)
    if missing:
        await message.answer(
            t("search.must_join", locale),
            reply_markup=force_join_keyboard(missing, locale),
        )
        return
    await message.answer(t("search.prompt", locale))


@router.message(
    F.text,
    ~F.text.startswith("🔍"),
    ~F.text.startswith("/"),
    IsSubscribed(),
)
async def handle_search_query(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    locale: UserLanguage = UserLanguage.EN,
) -> None:
    """Handles any free-text message as a search query (when not in a FSM state)."""
    current_state = await state.get_state()
    if current_state is not None:
        return  # Let FSM handlers take over

    query = message.text.strip()
    if len(query) < 2:
        await message.answer(t("search.query_too_short", locale))
        return

    movie_svc = MovieService(session)
    user_svc = UserService(session)
    results = await movie_svc.search(query)

    if not results:
        session.add(SearchLog(
            query=query, telegram_id=message.from_user.id, kind=SearchLogKind.MISS,
        ))
        sent = await message.answer(
            t("search.no_results", locale, query=query),
            reply_markup=await build_zero_result_keyboard(session, query, locale),
        )
        schedule_delete(sent.chat.id, sent.message_id)
        return

    user = await user_svc.get_by_telegram_id(message.from_user.id)
    watchlist_svc = WatchlistService(session)

    for movie in results[:5]:
        await movie_svc.increment_view(movie.id)
        in_watchlist = await watchlist_svc.is_in_watchlist(user.id, movie.id) if user else False
        sent = await send_movie_or_ppv_gate(
            message, movie, user,
            reply_markup_if_delivered=await build_delivered_movie_keyboard(session, movie.id, in_watchlist, locale),
        )
        schedule_delete(sent.chat.id, sent.message_id)


@router.message(F.text, ~IsSubscribed(), ~F.text.startswith("/"))
async def handle_not_subscribed(
    message: Message,
    bot: Bot,
    session: AsyncSession,
    locale: UserLanguage = UserLanguage.EN,
) -> None:
    # ~IsSubscribed() only tells us the user is blocked, not by which channels
    # (aiogram's filter inversion discards a filter's returned data) — so we
    # look the list up again here. One extra query, correct behaviour.
    missing = await get_missing_channels(bot, session, message.from_user.id)
    await message.answer(
        t("search.must_join", locale),
        reply_markup=force_join_keyboard(missing, locale),
    )


@router.callback_query(F.data == "check_subscription")
async def recheck_subscription(callback: CallbackQuery, session: AsyncSession, locale: UserLanguage = UserLanguage.EN) -> None:
    missing = await get_missing_channels(callback.bot, session, callback.from_user.id)
    if not missing:
        await callback.message.edit_text(t("search.subscription_ok", locale))
    else:
        await callback.message.edit_reply_markup(reply_markup=force_join_keyboard(missing, locale))
    await callback.answer()


@router.callback_query(F.data.startswith("watchlist:add:"))
async def add_to_watchlist(callback: CallbackQuery, session: AsyncSession, locale: UserLanguage = UserLanguage.EN) -> None:
    movie_id = int(callback.data.split(":")[2])

    user_svc = UserService(session)
    user = await user_svc.get_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer(t("search.not_found_alert", locale), show_alert=True)
        return

    added = await WatchlistService(session).add(user.id, movie_id)
    await callback.answer(
        t("search.watchlist_added" if added else "search.watchlist_already", user.language), show_alert=True
    )


@router.callback_query(F.data.startswith("watchlist:remove:"))
async def remove_from_watchlist(callback: CallbackQuery, session: AsyncSession, locale: UserLanguage = UserLanguage.EN) -> None:
    movie_id = int(callback.data.split(":")[2])

    user_svc = UserService(session)
    user = await user_svc.get_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer(t("search.not_found_alert", locale), show_alert=True)
        return

    removed = await WatchlistService(session).remove(user.id, movie_id)
    await callback.answer(
        t("search.watchlist_removed" if removed else "search.watchlist_not_in", user.language), show_alert=True
    )


@router.callback_query(F.data.startswith("report_broken:"))
async def report_broken(callback: CallbackQuery, session: AsyncSession, locale: UserLanguage = UserLanguage.EN) -> None:
    movie_id = int(callback.data.split(":")[1])
    movie_svc = MovieService(session)
    await movie_svc.mark_broken(movie_id)
    await callback.answer(t("search.reported", locale), show_alert=True)


@router.callback_query(F.data.startswith("request_movie:"))
async def request_movie(callback: CallbackQuery, session: AsyncSession, locale: UserLanguage = UserLanguage.EN) -> None:
    query = callback.data.split(":", 1)[1]
    session.add(SearchLog(
        query=query, telegram_id=callback.from_user.id, kind=SearchLogKind.REQUEST,
    ))
    logger.info("Movie requested: %r by user %d", query, callback.from_user.id)
    await callback.answer(t("search.request_logged", locale), show_alert=True)

    # The request was already being saved correctly (visible via 📊
    # Analytics → 📣 Search Log), but nothing ever told an admin a new one
    # had come in — they'd only see it if they remembered to go check.
    # A push notification is what actually makes requests "visible."
    # Admin-facing, so it deliberately stays fixed English rather than
    # routing through t() — see the "Zero Hardcoding" summary for why
    # admin-only screens are out of scope for this system.
    for admin_id in settings.ADMIN_IDS:
        try:
            await callback.bot.send_message(admin_id, f"📣 New movie request: <b>{query}</b>")
        except Exception:
            pass
