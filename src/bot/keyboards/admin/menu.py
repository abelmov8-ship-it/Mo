from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database.models.menu_button import MenuButton, MenuButtonAction, MenuButtonType

ACTION_LABELS = {
    MenuButtonAction.SEARCH: "🔍 Search",
    MenuButtonAction.CHANNELS: "🎬 Movie Channels",
    MenuButtonAction.TRENDING: "🔥 Trending & New",
    MenuButtonAction.REFERRAL: "📢 Referral",
    MenuButtonAction.VIP_PACKAGE: "💎 VIP Package",
    MenuButtonAction.PAYMENT: "💳 Payment",
    MenuButtonAction.PHOTO_EDITOR: "🎨 Photo Editor",
    MenuButtonAction.PROFILE: "👤 Profile",
    MenuButtonAction.LANGUAGE: "🌐 Language",
    MenuButtonAction.SUPPORT: "🆘 Support",
}


def menu_list_keyboard(buttons: list[MenuButton]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Add Button", callback_data="menuadm:add")
    for btn in buttons:
        vis_icon = "🟢" if btn.is_visible else "🔴"
        type_icon = "📌" if btn.keyboard_type == MenuButtonType.REPLY else "💬"
        builder.button(text=f"{vis_icon}{type_icon} {btn.label}", callback_data=f"menuadm:manage:{btn.id}")
    builder.adjust(1)
    return builder.as_markup()


def menu_manage_keyboard(btn: MenuButton, *, is_first: bool, is_last: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    vis_label = "🔴 Hide" if btn.is_visible else "🟢 Show"
    type_label = "💬 Switch to Inline" if btn.keyboard_type == MenuButtonType.REPLY else "📌 Switch to Reply"
    builder.button(text="✏️ Edit English Label", callback_data=f"menuadm:edit_label:en:{btn.id}")
    builder.button(text="✏️ Edit Amharic Label", callback_data=f"menuadm:edit_label:am:{btn.id}")
    if btn.label_am:
        builder.button(text="♻️ Clear Amharic Label", callback_data=f"menuadm:clear_label_am:{btn.id}")
    builder.button(text=vis_label, callback_data=f"menuadm:toggle_vis:{btn.id}")
    builder.button(text=type_label, callback_data=f"menuadm:toggle_type:{btn.id}")
    if not is_first:
        builder.button(text="⬆️ Move Up", callback_data=f"menuadm:move:{btn.id}:up")
    if not is_last:
        builder.button(text="⬇️ Move Down", callback_data=f"menuadm:move:{btn.id}:down")
    builder.button(text="🗑️ Delete", callback_data=f"menuadm:delete:{btn.id}")
    builder.button(text="⬅️ Back to List", callback_data="menuadm:list")
    builder.adjust(1)
    return builder.as_markup()


def action_picker_keyboard() -> InlineKeyboardMarkup:
    """Step 1 of the add wizard — admin picks WHAT the button does. The
    label (what it's called) is a separate step, kept deliberately apart so
    it's obvious in the UI itself that these are two independent things."""
    builder = InlineKeyboardBuilder()
    for action, label in ACTION_LABELS.items():
        builder.button(text=label, callback_data=f"menuadm:wiz:action:{action.value}")
    builder.button(text="⬅️ Cancel", callback_data="menuadm:list")
    builder.adjust(2)
    return builder.as_markup()


def keyboard_type_picker() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📌 Reply Keyboard", callback_data="menuadm:wiz:type:reply")
    builder.button(text="💬 Inline Keyboard", callback_data="menuadm:wiz:type:inline")
    builder.adjust(1)
    return builder.as_markup()
