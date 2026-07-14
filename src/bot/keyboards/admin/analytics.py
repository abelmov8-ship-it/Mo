from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def analytics_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔗 Broken Links"), KeyboardButton(text="📣 Search Log")],
            [KeyboardButton(text="🔘 Delivery Buttons")],
            [KeyboardButton(text="⬅️ Back to Admin")],
        ],
        resize_keyboard=True,
    )
