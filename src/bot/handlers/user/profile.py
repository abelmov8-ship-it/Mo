from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models.menu_button import MenuButtonAction
from bot.database.models.user import UserLanguage
from bot.filters.menu_action import MenuAction
from bot.services.user_service import UserService
from bot.services.watchlist_service import WatchlistService
from bot.utils.formatters import format_profile
from bot.utils.i18n import t

router = Router(name="user:profile")

# ponytail: a hard display cap, not real pagination — a personal watchlist
# realistically stays well under this in practice, and Next/Prev machinery
# for it isn't worth building until someone actually needs it. If that
# changes, inline_menu_keyboard's two-builder pagination pattern
# (keyboards/user/main_menu.py) is the template to reuse.
MAX_WATCHLIST_DISPLAY = 20


def _profile_keyboard(locale: UserLanguage) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("profile.watchlist_button", locale), callback_data="profile:watchlist")
    return builder.as_markup()


def _watchlist_keyboard(movies: list, locale: UserLanguage) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for movie in movies[:MAX_WATCHLIST_DISPLAY]:
        short_title = movie.title[:30] + ("…" if len(movie.title) > 30 else "")
        builder.button(
            text=t("profile.watchlist_remove_button", locale, title=short_title),
            callback_data=f"mywatchlist:remove:{movie.id}",
        )
    builder.adjust(1)
    return builder.as_markup()


def _watchlist_text(movies: list, locale: UserLanguage) -> str:
    if not movies:
        return t("profile.watchlist_empty", locale)
    header = t("profile.watchlist_header", locale, count=len(movies))
    if len(movies) > MAX_WATCHLIST_DISPLAY:
        header += t("profile.watchlist_showing_recent", locale, max=MAX_WATCHLIST_DISPLAY)
    return header


@router.message(MenuAction(MenuButtonAction.PROFILE))
async def show_profile(message: Message, session: AsyncSession) -> None:
    user_svc = UserService(session)
    user = await user_svc.get_by_telegram_id(message.from_user.id)
    if not user:
        await message.answer(t("profile.not_found"))
        return

    sub = await user_svc.get_active_subscription(user)
    await message.answer(
        format_profile(user, sub, locale=user.language),
        reply_markup=_profile_keyboard(user.language),
    )


@router.callback_query(F.data == "profile:watchlist")
async def show_watchlist(callback: CallbackQuery, session: AsyncSession) -> None:
    user_svc = UserService(session)
    user = await user_svc.get_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer(t("profile.not_found_alert"), show_alert=True)
        return

    movies = await WatchlistService(session).get_for_user(user.id)
    await callback.message.edit_text(
        _watchlist_text(movies, user.language), reply_markup=_watchlist_keyboard(movies, user.language)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("mywatchlist:remove:"))
async def remove_from_watchlist_view(callback: CallbackQuery, session: AsyncSession) -> None:
    movie_id = int(callback.data.split(":")[2])

    user_svc = UserService(session)
    user = await user_svc.get_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer(t("profile.not_found_alert"), show_alert=True)
        return

    await WatchlistService(session).remove(user.id, movie_id)
    await callback.answer(t("profile.watchlist_removed", user.language))

    movies = await WatchlistService(session).get_for_user(user.id)
    await callback.message.edit_text(
        _watchlist_text(movies, user.language), reply_markup=_watchlist_keyboard(movies, user.language)
    )
