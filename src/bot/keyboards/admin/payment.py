from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def payment_admin_keyboard() -> InlineKeyboardMarkup:
    """Top-level payment management menu."""
    builder = InlineKeyboardBuilder()
    builder.button(text="⏳ Pending Receipts",    callback_data="admin_pay:pending")
    builder.button(text="🏦 Manage Banks",         callback_data="admin_pay:banks")
    builder.button(text="💎 VIP Pricing",          callback_data="admin_pay:pricing")
    builder.button(text="⚙️ Chapa Settings",       callback_data="admin_pay:chapa")
    builder.button(text="👛 Wallet Settings",      callback_data="admin_pay:wallet")
    builder.adjust(1)
    return builder.as_markup()


def receipt_action_keyboard(payment_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Approve", callback_data=f"receipt:approve:{payment_id}")
    builder.button(text="❌ Reject",  callback_data=f"receipt:reject:{payment_id}")
    builder.adjust(2)
    return builder.as_markup()


def bank_list_keyboard(banks: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Add Bank Account", callback_data="bank:add")
    for bank in banks:
        builder.button(
            text=f"✏️ {bank['name']}",
            callback_data=f"bank:edit:{bank['id']}",
        )
        builder.button(
            text=f"🗑️ Delete",
            callback_data=f"bank:delete:{bank['id']}",
        )
    builder.adjust(1)
    return builder.as_markup()


def chapa_settings_keyboard(enabled: bool) -> InlineKeyboardMarkup:
    status = "🟢 ON" if enabled else "🔴 OFF"
    builder = InlineKeyboardBuilder()
    builder.button(text=f"⚙️ Chapa: {status}",  callback_data="admin:toggle_chapa")
    builder.button(text="🔑 Update API Key",     callback_data="admin:update_chapa_key")
    builder.button(text="🔐 Update Webhook Secret", callback_data="admin:update_chapa_webhook_secret")
    builder.adjust(1)
    return builder.as_markup()


def wallet_settings_keyboard(topup_enabled: bool) -> InlineKeyboardMarkup:
    status = "🟢 ON" if topup_enabled else "🔴 OFF"
    builder = InlineKeyboardBuilder()
    builder.button(text=f"👛 Top-up: {status}", callback_data="admin:toggle_wallet_topup")
    builder.adjust(1)
    return builder.as_markup()
