from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def faq_list_keyboard(entries: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Add FAQ Entry", callback_data="faqadm:add")
    for entry in sorted(entries, key=lambda e: e.get("order", 0)):
        vis_icon = "🟢" if entry.get("is_visible", True) else "🔴"
        builder.button(text=f"{vis_icon} {entry['question']}", callback_data=f"faqadm:manage:{entry['id']}")
    builder.button(text="⬅️ Back", callback_data="bc:menu")
    builder.adjust(1)
    return builder.as_markup()


def faq_manage_keyboard(entry: dict, *, is_first: bool, is_last: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    vis_label = "🔴 Hide" if entry.get("is_visible", True) else "🟢 Show"
    builder.button(text="✏️ Edit Question", callback_data=f"faqadm:edit_q:{entry['id']}")
    builder.button(text="✏️ Edit Answer", callback_data=f"faqadm:edit_a:{entry['id']}")
    builder.button(text=vis_label, callback_data=f"faqadm:toggle_vis:{entry['id']}")
    if not is_first:
        builder.button(text="⬆️ Move Up", callback_data=f"faqadm:move:{entry['id']}:up")
    if not is_last:
        builder.button(text="⬇️ Move Down", callback_data=f"faqadm:move:{entry['id']}:down")
    builder.button(text="🗑️ Delete", callback_data=f"faqadm:delete:{entry['id']}")
    builder.button(text="⬅️ Back to List", callback_data="faqadm:list")
    builder.adjust(1)
    return builder.as_markup()
