from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models.movie import Movie, MovieFileType
from bot.database.models.user import User, UserLanguage
from bot.services.settings_service import SettingsService, button_label
from bot.utils.formatters import format_search_result
from bot.utils.i18n import t


async def deliver_movie(
    message: Message,
    movie: Movie,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
    caption: str | None = None,
    locale: UserLanguage = UserLanguage.EN,
) -> Message:
    """Sends a movie's actual file via the Telegram method that matches how
    it was uploaded. Every call site used to hardcode answer_document, which
    works but sends video/audio as a generic file, losing native
    inline playback."""
    caption = caption if caption is not None else format_search_result(movie.title, movie.file_id, 0, locale)
    if movie.file_type == MovieFileType.AUDIO:
        return await message.answer_audio(audio=movie.file_id, caption=caption, reply_markup=reply_markup)
    if movie.file_type == MovieFileType.VIDEO:
        return await message.answer_video(video=movie.file_id, caption=caption, reply_markup=reply_markup)
    return await message.answer_document(document=movie.file_id, caption=caption, reply_markup=reply_markup)


_VALID_URL_SCHEMES = ("http://", "https://", "tg://")


async def build_delivered_movie_keyboard(
    session: AsyncSession, movie_id: int, in_watchlist: bool = False, locale: UserLanguage = UserLanguage.EN,
) -> InlineKeyboardMarkup:
    """The full button set for an actually-delivered movie file: the
    configurable default slots (Watch Later, Report Broken Link) plus any
    admin-added custom buttons. This is the one place all three delivery
    call sites (search hits, PPV-unlock) build this keyboard, so they
    can't drift apart on what a delivered file shows — wallet.py's
    unlock_ppv used to attach no keyboard at all here, which this fixes
    as a side effect of centralizing it."""
    settings_svc = SettingsService(session)
    config = await settings_svc.get_default_button_config()
    custom_buttons = await settings_svc.get_movie_delivery_buttons()

    builder = InlineKeyboardBuilder()

    watch_later = config["watch_later"]
    if watch_later["enabled"]:
        label = t("movie.in_watchlist_label", locale) if in_watchlist else button_label(watch_later, locale)
        builder.button(
            text=label,
            callback_data=f"watchlist:{'remove' if in_watchlist else 'add'}:{movie_id}",
        )

    report_broken = config["report_broken"]
    if report_broken["enabled"]:
        builder.button(text=button_label(report_broken, locale), callback_data=f"report_broken:{movie_id}")

    # Render-time guard, not just save-time validation: a button with a
    # malformed url= makes Telegram reject the WHOLE sendMessage call, not
    # just that one button, so a bad value reaching this point (e.g. from
    # a future direct-DB edit) must not be able to break every other
    # button riding along with it.
    for btn in sorted((b for b in custom_buttons if b.get("is_visible", True)), key=lambda b: b.get("order", 0)):
        if btn["url"].startswith(_VALID_URL_SCHEMES):
            builder.button(text=button_label(btn, locale), url=btn["url"])

    builder.adjust(1)
    return builder.as_markup()


async def build_zero_result_keyboard(session: AsyncSession, query: str, locale: UserLanguage = UserLanguage.EN) -> InlineKeyboardMarkup:
    """The zero-result fallback keyboard: Request Movie (if enabled) plus
    every visible backup-channel link (previously a single URL, now a
    list — same config-driven approach as the delivered-movie keyboard
    above)."""
    settings_svc = SettingsService(session)
    config = await settings_svc.get_default_button_config()
    backup_links = await settings_svc.get_backup_channel_links()

    builder = InlineKeyboardBuilder()

    request_movie = config["request_movie"]
    if request_movie["enabled"]:
        builder.button(text=button_label(request_movie, locale), callback_data=f"request_movie:{query[:50]}")

    backup_channel = config["backup_channel"]
    if backup_channel["enabled"]:
        for link in sorted((l for l in backup_links if l.get("is_visible", True)), key=lambda l: l.get("order", 0)):
            if link["url"].startswith(_VALID_URL_SCHEMES):  # same render-time guard as above
                builder.button(text=button_label(link, locale), url=link["url"])

    builder.adjust(1)
    return builder.as_markup()


async def send_movie_or_ppv_gate(
    message: Message,
    movie: Movie,
    user: User | None,
    *,
    reply_markup_if_delivered: InlineKeyboardMarkup | None = None,
    caption_if_delivered: str | None = None,
) -> Message:
    """The PPV/VIP decision in one place: locked movies show the unlock
    keyboard instead of the file, unlocked ones get delivered. search.py had
    this; trending.py didn't have it at all, so every PPV movie was fully
    downloadable for free from Trending regardless of price — same rule,
    now enforced everywhere a movie can be reached from."""
    if movie.is_ppv and not (user and user.is_vip):
        from bot.keyboards.user.payment import ppv_unlock_keyboard  # avoids a circular import at module load

        locale = user.language if user else UserLanguage.EN
        wallet_ok = user is not None and user.wallet_balance >= movie.ppv_price
        return await message.answer(
            format_search_result(movie.title, movie.file_id, movie.ppv_price, locale),
            reply_markup=ppv_unlock_keyboard(movie.id, movie.ppv_price, wallet_ok, locale=locale),
        )
    return await deliver_movie(
        message, movie, reply_markup=reply_markup_if_delivered, caption=caption_if_delivered,
        locale=user.language if user else UserLanguage.EN,
    )
