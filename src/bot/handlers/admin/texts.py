from __future__ import annotations

import re
from html import escape as _escape_html

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.filters.is_admin import IsAdmin
from bot.fsm.admin import TextEditStates
from bot.keyboards.admin.texts import text_categories_keyboard, text_keys_keyboard, text_manage_keyboard
from bot.utils.i18n import current_value, known_keys, save_text_override

router = Router(name="admin:texts")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

_TAG_RE = re.compile(r"<(/?)(b|i|u|s|code|pre|a|tg-spoiler|blockquote)\b[^>]*>", re.IGNORECASE)


def _unbalanced_tags(text: str) -> list[str]:
    """Cheap open/close balance check for Telegram's supported HTML tags —
    not a full parser (doesn't check attributes or nesting order), just
    enough to catch a stray unclosed/mismatched tag before it breaks
    message delivery for every user who hits this key. Warns, doesn't
    block: a false positive here shouldn't stop an admin from saving text
    they've already confirmed is what they want."""
    stack: list[str] = []
    unmatched: list[str] = []
    for closing, tag in _TAG_RE.findall(text):
        tag = tag.lower()
        if not closing:
            stack.append(tag)
        elif stack and stack[-1] == tag:
            stack.pop()
        else:
            unmatched.append(tag)
    return stack + unmatched


def _categories() -> dict[str, int]:
    counts: dict[str, int] = {}
    for key in known_keys():
        category = key.split(".", 1)[0]
        counts[category] = counts.get(category, 0) + 1
    return dict(sorted(counts.items()))


def _keys_in(category: str) -> list[str]:
    return sorted(k for k in known_keys() if k.split(".", 1)[0] == category)


def _preview(value: str | None) -> str:
    """Templates routinely contain literal <b>/<code> etc. meant for the
    *user's* rendered message — showing them raw inside our own <code> block
    would have Telegram try to parse those as real entities nested inside
    <code>, which it rejects, so the admin's preview screen would fail to
    send entirely. Escaping first shows the admin exactly the characters to
    type, safely, instead."""
    if value is None:
        return "<i>— not set —</i>"
    shown = value if len(value) <= 200 else value[:200] + "…"
    return f"<code>{_escape_html(shown)}</code>"


def _manage_text(key: str) -> str:
    """The key/EN/AM summary shown on the manage screen — one place, since
    show/save/reset all land back on this same screen."""
    en_value, en_override = current_value(key, "en")
    am_value, am_override = current_value(key, "am")
    am_state = " (custom)" if am_override else (" (default)" if am_value else " (not set — falls back to English)")
    return (
        f"📝 <code>{key}</code>\n\n"
        f"🇬🇧 English{' (custom)' if en_override else ' (default)'}:\n{_preview(en_value)}\n\n"
        f"🇪🇹 Amharic{am_state}:\n{_preview(am_value)}"
    )


def _manage_keyboard(key: str):
    category = key.split(".", 1)[0]
    _, en_override = current_value(key, "en")
    _, am_override = current_value(key, "am")
    return text_manage_keyboard(key, category, en_override, am_override)


@router.callback_query(F.data == "txtadm:cats")
async def show_categories(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(
        "📝 <b>Bot Texts</b>\n\n"
        "Every message and button the bot sends, grouped by section. Each "
        "one can have an English and/or Amharic version — leave one blank "
        "and it falls back to the other (English is the last-resort "
        "fallback if neither is set).",
        reply_markup=text_categories_keyboard(_categories()),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("txtadm:cat:"))
async def show_keys(callback: CallbackQuery) -> None:
    _, _, category, page_str = callback.data.split(":")
    keys = _keys_in(category)
    overridden = {k for k in keys if current_value(k, "en")[1] or current_value(k, "am")[1]}
    await callback.message.edit_text(
        f"📝 <b>{category.title()}</b>\n\n✏️ = has a custom override. Tap a key to manage it.",
        reply_markup=text_keys_keyboard(category, keys, int(page_str), overridden),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("txtadm:key:"))
async def manage_key(callback: CallbackQuery) -> None:
    key = callback.data.split(":", 2)[2]
    await callback.message.edit_text(_manage_text(key), reply_markup=_manage_keyboard(key))
    await callback.answer()


@router.callback_query(F.data.startswith("txtadm:edit:"))
async def prompt_edit(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, key, lang = callback.data.split(":")
    await state.update_data(key=key, lang=lang)
    await state.set_state(TextEditStates.entering_value)
    lang_name = "English" if lang == "en" else "Amharic"
    current, _ = current_value(key, lang)
    await callback.message.edit_text(
        f"✏️ Send the new <b>{lang_name}</b> text for <code>{key}</code>.\n\n"
        f"Current:\n{_preview(current)}\n\n"
        "Keep any <code>{placeholders}</code> from the current text — "
        "they get filled in with real values when the bot sends it."
    )
    await callback.answer()


@router.message(TextEditStates.entering_value)
async def save_edit(message: Message, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    key, lang = data.get("key"), data.get("lang")
    await state.clear()
    if not key or not lang or not message.text:
        return

    await save_text_override(session, key, lang, message.text)

    warning = ""
    bad_tags = _unbalanced_tags(message.text)
    if bad_tags:
        warning = (
            f"\n\n⚠️ This looks like it might have an unclosed or mismatched "
            f"HTML tag ({', '.join(sorted(set(bad_tags)))}) — saved anyway, "
            f"but double-check it or messages using this key may fail to send."
        )

    await message.answer(f"✅ Saved.{warning}\n\n{_manage_text(key)}", reply_markup=_manage_keyboard(key))


@router.callback_query(F.data.startswith("txtadm:reset:"))
async def reset_value(callback: CallbackQuery, session: AsyncSession) -> None:
    _, _, key, lang = callback.data.split(":")
    await save_text_override(session, key, lang, "")
    await callback.message.edit_text(f"♻️ Reset to default.\n\n{_manage_text(key)}", reply_markup=_manage_keyboard(key))
    await callback.answer()


@router.callback_query(F.data == "txtadm:noop")
async def noop(callback: CallbackQuery) -> None:
    await callback.answer()
