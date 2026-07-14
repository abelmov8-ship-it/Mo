from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

SLOT_TITLES = {
    "watch_later": "Watch Later",
    "report_broken": "Report Broken Link",
    "request_movie": "Request Movie",
    "backup_channel": "Check Backup Channel",
}


def delivery_buttons_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔘 Default Buttons", callback_data="delbtn:defaults")
    builder.button(text="🔗 Custom File Buttons", callback_data="delbtn:custom:list")
    builder.button(text="🔗 Backup Channel Links", callback_data="delbtn:backup:list")
    builder.adjust(1)
    return builder.as_markup()


def default_buttons_list_keyboard(config: dict) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for slot, title in SLOT_TITLES.items():
        state = config.get(slot, {})
        icon = "🟢" if state.get("enabled", True) else "🔴"
        builder.button(text=f"{icon} {title}", callback_data=f"delbtn:default:manage:{slot}")
    builder.button(text="⬅️ Back", callback_data="delbtn:menu")
    builder.adjust(1)
    return builder.as_markup()


def default_button_manage_keyboard(slot: str, enabled: bool, has_label_am: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Edit English Label", callback_data=f"delbtn:default:edit_label:en:{slot}")
    builder.button(text="✏️ Edit Amharic Label", callback_data=f"delbtn:default:edit_label:am:{slot}")
    if has_label_am:
        builder.button(text="♻️ Clear Amharic Label", callback_data=f"delbtn:default:clear_label_am:{slot}")
    builder.button(text=("🔴 Turn Off" if enabled else "🟢 Turn On"), callback_data=f"delbtn:default:toggle:{slot}")
    builder.button(text="⬅️ Back to List", callback_data="delbtn:defaults")
    builder.adjust(1)
    return builder.as_markup()


def custom_buttons_list_keyboard(buttons: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Add Button", callback_data="delbtn:custom:add")
    for btn in sorted(buttons, key=lambda b: b.get("order", 0)):
        icon = "🟢" if btn.get("is_visible", True) else "🔴"
        builder.button(text=f"{icon} {btn['label']}", callback_data=f"delbtn:custom:manage:{btn['id']}")
    builder.button(text="⬅️ Back", callback_data="delbtn:menu")
    builder.adjust(1)
    return builder.as_markup()


def custom_button_manage_keyboard(btn: dict, *, is_first: bool, is_last: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    vis_label = "🔴 Hide" if btn.get("is_visible", True) else "🟢 Show"
    builder.button(text="✏️ Edit English Label", callback_data=f"delbtn:custom:edit_label:en:{btn['id']}")
    builder.button(text="✏️ Edit Amharic Label", callback_data=f"delbtn:custom:edit_label:am:{btn['id']}")
    if btn.get("label_am"):
        builder.button(text="♻️ Clear Amharic Label", callback_data=f"delbtn:custom:clear_label_am:{btn['id']}")
    builder.button(text="🔗 Edit URL", callback_data=f"delbtn:custom:edit_url:{btn['id']}")
    builder.button(text=vis_label, callback_data=f"delbtn:custom:toggle_vis:{btn['id']}")
    if not is_first:
        builder.button(text="⬆️ Move Up", callback_data=f"delbtn:custom:move:{btn['id']}:up")
    if not is_last:
        builder.button(text="⬇️ Move Down", callback_data=f"delbtn:custom:move:{btn['id']}:down")
    builder.button(text="🗑️ Delete", callback_data=f"delbtn:custom:delete:{btn['id']}")
    builder.button(text="⬅️ Back to List", callback_data="delbtn:custom:list")
    builder.adjust(1)
    return builder.as_markup()


def backup_links_list_keyboard(links: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Add Link", callback_data="delbtn:backup:add")
    for link in sorted(links, key=lambda l: l.get("order", 0)):
        icon = "🟢" if link.get("is_visible", True) else "🔴"
        builder.button(text=f"{icon} {link['label']}", callback_data=f"delbtn:backup:manage:{link['id']}")
    builder.button(text="⬅️ Back", callback_data="delbtn:menu")
    builder.adjust(1)
    return builder.as_markup()


def backup_link_manage_keyboard(link: dict, *, is_first: bool, is_last: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    vis_label = "🔴 Hide" if link.get("is_visible", True) else "🟢 Show"
    builder.button(text="✏️ Edit English Label", callback_data=f"delbtn:backup:edit_label:en:{link['id']}")
    builder.button(text="✏️ Edit Amharic Label", callback_data=f"delbtn:backup:edit_label:am:{link['id']}")
    if link.get("label_am"):
        builder.button(text="♻️ Clear Amharic Label", callback_data=f"delbtn:backup:clear_label_am:{link['id']}")
    builder.button(text="🔗 Edit URL", callback_data=f"delbtn:backup:edit_url:{link['id']}")
    builder.button(text=vis_label, callback_data=f"delbtn:backup:toggle_vis:{link['id']}")
    if not is_first:
        builder.button(text="⬆️ Move Up", callback_data=f"delbtn:backup:move:{link['id']}:up")
    if not is_last:
        builder.button(text="⬇️ Move Down", callback_data=f"delbtn:backup:move:{link['id']}:down")
    builder.button(text="🗑️ Delete", callback_data=f"delbtn:backup:delete:{link['id']}")
    builder.button(text="⬅️ Back to List", callback_data="delbtn:backup:list")
    builder.adjust(1)
    return builder.as_markup()
