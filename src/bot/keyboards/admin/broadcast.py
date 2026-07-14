from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def audience_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="👥 All Users",     callback_data="bc:audience:all")
    builder.button(text="💎 VIP Only",      callback_data="bc:audience:vip")
    builder.button(text="📝 Edit Welcome",  callback_data="bc:edit_welcome")
    builder.adjust(1)
    return builder.as_markup()


def welcome_language_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🇬🇧 English Welcome", callback_data="welcome:lang:en")
    builder.button(text="🇪🇹 Amharic Welcome", callback_data="welcome:lang:am")
    builder.button(text="⬅️ Back",              callback_data="bc:back")
    builder.adjust(1)
    return builder.as_markup()


def broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Send Now",  callback_data="bc:confirm")
    builder.button(text="❌ Cancel",    callback_data="bc:cancel")
    builder.adjust(2)
    return builder.as_markup()


def broadcast_buttons_keyboard() -> InlineKeyboardMarkup:
    """Optional interactive buttons to attach to the broadcast message."""
    builder = InlineKeyboardBuilder()
    builder.button(text="👍 / 👎 Reactions", callback_data="bc:btn:reactions")
    builder.button(text="🔗 Share Link",     callback_data="bc:btn:share")
    builder.button(text="➡️ Skip Buttons",   callback_data="bc:btn:skip")
    builder.adjust(1)
    return builder.as_markup()
