from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def admin_panel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📢 Broadcast"),       KeyboardButton(text="📊 Analytics")],
            [KeyboardButton(text="🎬 Channels"),        KeyboardButton(text="💳 Payments")],
            [KeyboardButton(text="⚙️ System Tools"),   KeyboardButton(text="📤 Post to Channel")],
            [KeyboardButton(text="🔗 Menu Builder"),     KeyboardButton(text="🖼 Trending Posters")],
            [KeyboardButton(text="⬅️ Back to Main Menu")],
        ],
        resize_keyboard=True,
    )


def payment_receipt_keyboard(payment_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Approve", callback_data=f"receipt:approve:{payment_id}")
    builder.button(text="❌ Reject",  callback_data=f"receipt:reject:{payment_id}")
    builder.adjust(2)
    return builder.as_markup()


