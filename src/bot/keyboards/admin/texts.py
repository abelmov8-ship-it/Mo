from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

KEY_PAGE_SIZE = 8


def text_categories_keyboard(counts: dict[str, int]) -> InlineKeyboardMarkup:
    """counts: {category: number_of_keys}."""
    builder = InlineKeyboardBuilder()
    for category, count in counts.items():
        builder.button(text=f"{category.title()} ({count})", callback_data=f"txtadm:cat:{category}:0")
    builder.button(text="⬅️ Back", callback_data="bc:menu")
    builder.adjust(2)
    return builder.as_markup()


def text_keys_keyboard(category: str, keys: list[str], page: int, overridden: set[str]) -> InlineKeyboardMarkup:
    """keys: every key in this category — pagination is done here, same
    slice-then-nav-row shape as inline_menu_keyboard in keyboards/user."""
    page_count = max(1, (len(keys) - 1) // KEY_PAGE_SIZE + 1)
    page = max(0, min(page, page_count - 1))
    start = page * KEY_PAGE_SIZE
    page_keys = keys[start:start + KEY_PAGE_SIZE]

    content = InlineKeyboardBuilder()
    for key in page_keys:
        suffix = key.split(".", 1)[1] if "." in key else key
        mark = "✏️ " if key in overridden else ""
        content.button(text=f"{mark}{suffix}", callback_data=f"txtadm:key:{key}")
    content.adjust(1)
    rows = content.export()

    if page_count > 1:
        nav = InlineKeyboardBuilder()
        if page > 0:
            nav.button(text="◀️ Prev", callback_data=f"txtadm:cat:{category}:{page - 1}")
        nav.button(text=f"{page + 1}/{page_count}", callback_data="txtadm:noop")
        if page < page_count - 1:
            nav.button(text="Next ▶️", callback_data=f"txtadm:cat:{category}:{page + 1}")
        nav.adjust(3)
        rows += nav.export()

    back = InlineKeyboardBuilder()
    back.button(text="⬅️ Categories", callback_data="txtadm:cats")
    rows += back.export()

    return InlineKeyboardMarkup(inline_keyboard=rows)


def text_manage_keyboard(key: str, category: str, has_en_override: bool, has_am_override: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Edit English", callback_data=f"txtadm:edit:{key}:en")
    builder.button(text="✏️ Edit Amharic", callback_data=f"txtadm:edit:{key}:am")
    if has_en_override:
        builder.button(text="♻️ Reset English to default", callback_data=f"txtadm:reset:{key}:en")
    if has_am_override:
        builder.button(text="♻️ Reset Amharic to default", callback_data=f"txtadm:reset:{key}:am")
    builder.button(text="⬅️ Back to List", callback_data=f"txtadm:cat:{category}:0")
    builder.adjust(1)
    return builder.as_markup()
