from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database.models.channel import Channel
from bot.database.models.user import UserLanguage
from bot.utils.i18n import t


def force_join_keyboard(missing_channels: list[Channel], locale: UserLanguage = UserLanguage.EN) -> InlineKeyboardMarkup:
    """Shown when the user hasn't joined all required channels."""
    builder = InlineKeyboardBuilder()
    for ch in missing_channels:
        builder.button(text=t("search.join_button", locale, name=ch.name), url=ch.url)
    builder.button(text=t("search.check_again_button", locale), callback_data="check_subscription")
    builder.adjust(1)
    return builder.as_markup()
