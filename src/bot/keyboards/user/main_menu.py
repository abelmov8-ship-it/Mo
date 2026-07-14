from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from bot.database.models.menu_button import MenuButton
from bot.database.models.user import UserLanguage
from bot.services.settings_service import button_label
from bot.utils.i18n import t

# ponytail: inline keyboards visually degrade well before Telegram's 100-button
# hard limit, so they get real Next/Prev pagination below. Reply keyboards
# don't have that problem the same way — Telegram's clients already scroll a
# tall persistent keyboard natively — so admin-added reply buttons are just
# rendered in full rather than given a second, more awkward pagination
# protocol (no callback_data to hang page state on; it'd need a stored FSM
# cursor and synthetic "More/Back" buttons). If a real need for that shows up,
# the cursor pattern from inline_menu_keyboard's `page` param is the template.
INLINE_PAGE_SIZE = 8


def reply_menu_keyboard(
    buttons: list[MenuButton], is_admin: bool = False, locale: UserLanguage = UserLanguage.EN,
) -> ReplyKeyboardMarkup | None:
    if not buttons and not is_admin:
        return None

    builder = ReplyKeyboardBuilder()
    for btn in buttons:
        builder.button(text=btn.display_label(locale))
    builder.adjust(2)

    if is_admin:
        # Deliberately outside the dynamic system — see MenuButtonAction's
        # docstring for why the admin's own way in must not be hideable.
        builder.row(KeyboardButton(text="🛠 Admin Panel"))

    return builder.as_markup(resize_keyboard=True)


def inline_menu_keyboard(buttons: list[MenuButton], page: int = 0, locale: UserLanguage = UserLanguage.EN) -> InlineKeyboardMarkup | None:
    if not buttons:
        return None

    page_count = (len(buttons) - 1) // INLINE_PAGE_SIZE + 1
    page = max(0, min(page, page_count - 1))
    start = page * INLINE_PAGE_SIZE
    page_buttons = buttons[start:start + INLINE_PAGE_SIZE]

    content = InlineKeyboardBuilder()
    for btn in page_buttons:
        content.button(text=btn.display_label(locale), callback_data=f"menu:go:{btn.action.value}")
    content.adjust(2)
    rows = content.export()

    if page_count > 1:
        # Built as its own builder and appended as a whole row, rather than
        # feeding nav buttons into the same adjust() call as the content —
        # that packed a lone trailing content button into the nav row
        # instead of giving it its own, since adjust() fills declared row
        # sizes greedily without knowing content and nav are semantically
        # different groups.
        nav = InlineKeyboardBuilder()
        if page > 0:
            nav.button(text=t("ui.prev", locale), callback_data=f"menu:page:{page - 1}")
        nav.button(text=f"{page + 1}/{page_count}", callback_data="menu:noop")
        if page < page_count - 1:
            nav.button(text=t("ui.next", locale), callback_data=f"menu:page:{page + 1}")
        nav.adjust(3)
        rows += nav.export()

    return InlineKeyboardMarkup(inline_keyboard=rows)


WELCOME_PAGE_SIZE = 4


def welcome_buttons_keyboard(
    buttons: list[dict], page: int = 0, *, paginated: bool = True, locale: UserLanguage = UserLanguage.EN,
) -> InlineKeyboardMarkup | None:
    """buttons are plain dicts from SettingsService.get_welcome_buttons(),
    not ORM rows — {"id", "label", "label_am", "url", "is_visible", "order"}
    (label_am is optional; older/unedited entries simply won't have the key).
    paginated=False (the admin's nav-off state) renders every visible
    button in one keyboard instead of hiding the ones past page 1; toggling
    navigation off must not make buttons unreachable."""
    visible = sorted(
        (b for b in buttons if b.get("is_visible", True)),
        key=lambda b: b.get("order", 0),
    )
    if not visible:
        return None

    if not paginated:
        content = InlineKeyboardBuilder()
        for b in visible:
            content.button(text=button_label(b, locale), url=b["url"])
        content.adjust(2)
        return content.as_markup()

    page_count = (len(visible) - 1) // WELCOME_PAGE_SIZE + 1
    page = max(0, min(page, page_count - 1))
    start = page * WELCOME_PAGE_SIZE
    page_buttons = visible[start:start + WELCOME_PAGE_SIZE]

    content = InlineKeyboardBuilder()
    for b in page_buttons:
        content.button(text=button_label(b, locale), url=b["url"])
    content.adjust(2)
    rows = content.export()

    if page_count > 1:
        nav = InlineKeyboardBuilder()
        if page > 0:
            nav.button(text=t("ui.prev", locale), callback_data=f"wbtn:page:{page - 1}")
        nav.button(text=f"{page + 1}/{page_count}", callback_data="menu:noop")  # reuses start.py's existing no-op handler
        if page < page_count - 1:
            nav.button(text=t("ui.next", locale), callback_data=f"wbtn:page:{page + 1}")
        nav.adjust(3)
        rows += nav.export()

    return InlineKeyboardMarkup(inline_keyboard=rows)


def language_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🇬🇧 English"), KeyboardButton(text="🇪🇹 አማርኛ")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
