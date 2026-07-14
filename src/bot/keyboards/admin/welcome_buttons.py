from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def welcome_buttons_list_keyboard(buttons: list[dict], nav_enabled: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Add Button", callback_data="wbtnadm:add")
    nav_label = "🔴 Turn Pagination Off" if nav_enabled else "🟢 Turn Pagination On"
    builder.button(text=nav_label, callback_data="wbtnadm:toggle_nav")
    for btn in sorted(buttons, key=lambda b: b.get("order", 0)):
        vis_icon = "🟢" if btn.get("is_visible", True) else "🔴"
        builder.button(text=f"{vis_icon} {btn['label']}", callback_data=f"wbtnadm:manage:{btn['id']}")
    builder.button(text="⬅️ Back", callback_data="bc:menu")
    builder.adjust(1)
    return builder.as_markup()


def welcome_button_manage_keyboard(btn: dict, *, is_first: bool, is_last: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    vis_label = "🔴 Hide" if btn.get("is_visible", True) else "🟢 Show"
    builder.button(text="✏️ Edit English Label", callback_data=f"wbtnadm:edit_label:en:{btn['id']}")
    builder.button(text="✏️ Edit Amharic Label", callback_data=f"wbtnadm:edit_label:am:{btn['id']}")
    if btn.get("label_am"):
        builder.button(text="♻️ Clear Amharic Label", callback_data=f"wbtnadm:clear_label_am:{btn['id']}")
    builder.button(text="🔗 Edit URL", callback_data=f"wbtnadm:edit_url:{btn['id']}")
    builder.button(text=vis_label, callback_data=f"wbtnadm:toggle_vis:{btn['id']}")
    if not is_first:
        builder.button(text="⬆️ Move Up", callback_data=f"wbtnadm:move:{btn['id']}:up")
    if not is_last:
        builder.button(text="⬇️ Move Down", callback_data=f"wbtnadm:move:{btn['id']}:down")
    builder.button(text="🗑️ Delete", callback_data=f"wbtnadm:delete:{btn['id']}")
    builder.button(text="⬅️ Back to List", callback_data="wbtnadm:list")
    builder.adjust(1)
    return builder.as_markup()
