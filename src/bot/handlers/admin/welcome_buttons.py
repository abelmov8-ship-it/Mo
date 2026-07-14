from __future__ import annotations

from html import escape as _escape_html

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.filters.is_admin import IsAdmin
from bot.fsm.admin import WelcomeButtonStates
from bot.keyboards.admin.welcome_buttons import welcome_button_manage_keyboard, welcome_buttons_list_keyboard
from bot.services.settings_service import SettingsService

router = Router(name="admin:welcome_buttons")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

# ponytail: not a full RFC 3986 validator — just enough to catch the most
# common admin mistake (pasting a bare domain without a scheme) before it
# becomes a Telegram InlineKeyboardButton that silently fails to open.
# Telegram's own API still does final validation on send.
_VALID_SCHEMES = ("http://", "https://", "tg://")


def validate_button_url(raw: str) -> str | None:
    """Returns the trimmed URL if acceptable, else None. Pulled out as a
    pure function so the validation logic is unit-testable without a
    Telegram Message object."""
    url = raw.strip()
    if not url.lower().startswith(_VALID_SCHEMES):
        return None
    if len(url) > 512:
        return None
    return url


async def _render_list(session, text_target, *, edit: bool) -> None:
    svc = SettingsService(session)
    buttons = await svc.get_welcome_buttons()
    nav_enabled = await svc.get_bool("welcome_nav_enabled", default=True)
    text = (
        f"🔗 <b>Welcome Message Buttons</b> ({len(buttons)} total)\n\n"
        f"Pagination: {'🟢 On' if nav_enabled else '🔴 Off (all buttons shown at once)'}\n\n"
        "Tap a button to manage it."
    )
    markup = welcome_buttons_list_keyboard(buttons, nav_enabled)
    if edit:
        await text_target.edit_text(text, reply_markup=markup)
    else:
        await text_target.answer(text, reply_markup=markup)


@router.callback_query(F.data == "bc:manage_welcome_buttons")
async def open_welcome_buttons(callback: CallbackQuery, session) -> None:
    await _render_list(session, callback.message, edit=True)
    await callback.answer()


@router.callback_query(F.data == "wbtnadm:list")
async def back_to_list(callback: CallbackQuery, session, state: FSMContext) -> None:
    await state.clear()
    await _render_list(session, callback.message, edit=True)
    await callback.answer()


@router.callback_query(F.data == "wbtnadm:toggle_nav")
async def toggle_nav(callback: CallbackQuery, session) -> None:
    svc = SettingsService(session)
    current = await svc.get_bool("welcome_nav_enabled", default=True)
    await svc.set_bool("welcome_nav_enabled", not current)
    await callback.answer("Pagination updated.")
    await _render_list(session, callback.message, edit=True)


# ── Add wizard (2 steps: label, then URL) ──────────────────────────────────

@router.callback_query(F.data == "wbtnadm:add")
async def wizard_step1_label(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.update_data(label_lang="en")
    await state.set_state(WelcomeButtonStates.entering_label)
    await callback.message.edit_text(
        "Step 1/2 — Send the button's display text (e.g. 📱 Follow on TikTok):\n\n"
        "You can add an Amharic version afterward from this button's manage screen."
    )
    await callback.answer()


@router.message(WelcomeButtonStates.entering_label)
async def handle_label_input(message: Message, session, state: FSMContext) -> None:
    label = (message.text or "").strip()
    if not label:
        await message.answer("❌ Send some text for the button label.")
        return
    if len(label) > 64:
        await message.answer("❌ Keep it under 64 characters.")
        return

    data = await state.get_data()
    lang = data.get("label_lang", "en")

    if data.get("button_id_to_edit"):
        field = "label" if lang == "en" else "label_am"
        await SettingsService(session).update_welcome_button(data["button_id_to_edit"], **{field: label})
        await state.clear()
        await message.answer(f"✅ {'English' if lang == 'en' else 'Amharic'} label updated.")
        return

    await state.update_data(label=label)
    await state.set_state(WelcomeButtonStates.entering_url)
    await message.answer("Step 2/2 — Send the URL this button should open (must start with https://):")


@router.callback_query(F.data.startswith("wbtnadm:edit_url:"))
async def edit_url_start(callback: CallbackQuery, state: FSMContext) -> None:
    btn_id = int(callback.data.split(":")[2])
    await state.update_data(button_id_to_edit=btn_id)
    await state.set_state(WelcomeButtonStates.entering_url)
    await callback.message.edit_text("Send the new URL (must start with https://):")
    await callback.answer()


@router.message(WelcomeButtonStates.entering_url)
async def handle_url_input(message: Message, session, state: FSMContext) -> None:
    url = validate_button_url(message.text or "")
    if not url:
        await message.answer("❌ The URL must start with https:// (or http:// / tg://) and be under 512 characters. Try again:")
        return

    data = await state.get_data()
    svc = SettingsService(session)

    if data.get("button_id_to_edit"):
        await svc.update_welcome_button(data["button_id_to_edit"], url=url)
        await state.clear()
        await message.answer("✅ URL updated.")
        return

    await svc.add_welcome_button(label=data["label"], url=url)
    await state.clear()
    await message.answer(f"✅ Button <b>{_escape_html(data['label'])}</b> added to the welcome message.")


@router.callback_query(F.data.startswith("wbtnadm:clear_label_am:"))
async def clear_label_am(callback: CallbackQuery, session) -> None:
    btn_id = int(callback.data.split(":")[2])
    await SettingsService(session).update_welcome_button(btn_id, label_am=None)
    await callback.answer("Amharic label cleared.")
    await manage_button(callback, session)


@router.callback_query(F.data.startswith("wbtnadm:edit_label:"))
async def edit_label_start(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, lang, btn_id = callback.data.split(":")
    await state.update_data(button_id_to_edit=int(btn_id), label_lang=lang)
    await state.set_state(WelcomeButtonStates.entering_label)
    lang_name = "English" if lang == "en" else "Amharic"
    await callback.message.edit_text(f"Send the new {lang_name} button text:")
    await callback.answer()


# ── Manage existing button ──────────────────────────────────────────────────

@router.callback_query(F.data.startswith("wbtnadm:manage:"))
async def manage_button(callback: CallbackQuery, session) -> None:
    btn_id = int(callback.data.split(":")[2])
    svc = SettingsService(session)
    buttons = sorted(await svc.get_welcome_buttons(), key=lambda b: b.get("order", 0))
    btn = next((b for b in buttons if b["id"] == btn_id), None)
    if not btn:
        await callback.answer("Button not found.", show_alert=True)
        return

    idx = buttons.index(btn)
    label_am = btn.get("label_am")
    label_am_shown = f"<b>{_escape_html(label_am)}</b>" if label_am else "<i>not set — falls back to English</i>"
    await callback.message.edit_text(
        f"🇬🇧 <b>{_escape_html(btn['label'])}</b>\n"
        f"🇪🇹 {label_am_shown}\n"
        f"URL: {_escape_html(btn['url'])}\n"
        f"Visible: {'🟢 Yes' if btn.get('is_visible', True) else '🔴 Hidden'}",
        reply_markup=welcome_button_manage_keyboard(btn, is_first=(idx == 0), is_last=(idx == len(buttons) - 1)),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("wbtnadm:toggle_vis:"))
async def toggle_visibility(callback: CallbackQuery, session) -> None:
    btn_id = int(callback.data.split(":")[2])
    svc = SettingsService(session)
    buttons = await svc.get_welcome_buttons()
    btn = next((b for b in buttons if b["id"] == btn_id), None)
    if btn:
        await svc.update_welcome_button(btn_id, is_visible=not btn.get("is_visible", True))
        await callback.answer("Visibility updated.")
    await manage_button(callback, session)


@router.callback_query(F.data.startswith("wbtnadm:move:"))
async def move_button(callback: CallbackQuery, session) -> None:
    parts = callback.data.split(":")
    btn_id, direction = int(parts[2]), (-1 if parts[3] == "up" else 1)
    await SettingsService(session).move_welcome_button(btn_id, direction)
    await callback.answer()
    await manage_button(callback, session)


@router.callback_query(F.data.startswith("wbtnadm:delete:"))
async def delete_button(callback: CallbackQuery, session) -> None:
    btn_id = int(callback.data.split(":")[2])
    deleted = await SettingsService(session).delete_welcome_button(btn_id)
    msg = "✅ Button deleted." if deleted else "❌ Button not found."
    await callback.answer(msg, show_alert=True)
    await _render_list(session, callback.message, edit=True)
