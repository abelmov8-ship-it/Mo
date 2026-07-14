from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def system_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👤 Manage User"),   KeyboardButton(text="🎟️ Promo Codes")],
            [KeyboardButton(text="📂 File Manager"),  KeyboardButton(text="💾 DB Backup")],
            [KeyboardButton(text="📊 Export Excel"),  KeyboardButton(text="🛠️ Core Config")],
            [KeyboardButton(text="⬅️ Back to Admin")],
        ],
        resize_keyboard=True,
    )


def promo_type_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="💎 VIP Days Reward",     callback_data="promo:type:vip_days")
    builder.button(text="💰 Wallet Balance Credit", callback_data="promo:type:wallet_credit")
    builder.button(text="❌ Cancel",               callback_data="promo:cancel")
    builder.adjust(1)
    return builder.as_markup()


def promo_list_keyboard(codes: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Create New Code", callback_data="promo:create")
    for code in codes:
        remaining = "∞" if code.usage_limit is None else str(code.usage_limit - code.used_count)
        builder.button(
            text=f"🎟 {code.code}  ({remaining} left)",
            callback_data=f"promo:view:{code.id}",
        )
    builder.adjust(1)
    return builder.as_markup()


def export_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="👥 All Users",   callback_data="export:all")
    builder.button(text="💎 VIP Only",    callback_data="export:vip")
    builder.button(text="🚫 Banned Only", callback_data="export:banned")
    builder.adjust(1)
    return builder.as_markup()


def delete_timer_keyboard(current: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for label, mins in [("1 Min", 1), ("3 Min", 3), ("5 Min", 5), ("Never", 0)]:
        tick = " ✓" if mins == current else ""
        builder.button(text=f"{label}{tick}", callback_data=f"admin:set_timer:{mins}")
    builder.adjust(2)
    return builder.as_markup()


def maintenance_keyboard(enabled: bool) -> InlineKeyboardMarkup:
    status = "🟢 ON — users locked out" if enabled else "🔴 OFF — live"
    builder = InlineKeyboardBuilder()
    builder.button(text=f"🛠 Maintenance: {status}", callback_data="admin:toggle_maintenance")
    return builder.as_markup()


def keyboard_type_toggle_keyboard(current: str, toggle_callback_data: str) -> InlineKeyboardMarkup:
    """current is "reply" or "inline" — shared by both Channels Keyboard
    and Payment Keyboard in Core Config, since both are the exact same
    binary choice with nothing else specific to either one."""
    status = "📌 Reply Keyboard" if current == "reply" else "💬 Inline Keyboard"
    builder = InlineKeyboardBuilder()
    builder.button(text=f"Currently: {status} — tap to switch", callback_data=toggle_callback_data)
    return builder.as_markup()


def anti_spam_keyboard(threshold: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for n in [3, 5, 10, 20]:
        tick = " ✓" if n == threshold else ""
        builder.button(text=f"{n} clicks/s{tick}", callback_data=f"admin:set_spam_threshold:{n}")
    builder.adjust(2)
    return builder.as_markup()


def user_action_keyboard(user_id: int, is_banned: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Grant VIP Days",        callback_data=f"admin_user:grant_vip:{user_id}")
    builder.button(text="💰 Adjust Wallet",          callback_data=f"admin_user:wallet:{user_id}")
    ban_label = "🔓 Unban User" if is_banned else "🚫 Ban User"
    builder.button(text=ban_label, callback_data=f"admin_user:toggle_ban:{user_id}")
    builder.adjust(1)
    return builder.as_markup()
