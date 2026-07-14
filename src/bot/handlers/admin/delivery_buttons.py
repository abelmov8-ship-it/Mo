from __future__ import annotations

from html import escape as _escape_html

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.filters.is_admin import IsAdmin
from bot.fsm.admin import DeliveryButtonStates
from bot.handlers.admin.welcome_buttons import validate_button_url
from bot.keyboards.admin.delivery_buttons import (
    SLOT_TITLES,
    backup_link_manage_keyboard,
    backup_links_list_keyboard,
    custom_button_manage_keyboard,
    custom_buttons_list_keyboard,
    default_button_manage_keyboard,
    default_buttons_list_keyboard,
    delivery_buttons_menu_keyboard,
)
from bot.services.settings_service import SettingsService

router = Router(name="admin:delivery_buttons")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


def normalize_channel_url(raw: str) -> str | None:
    """More forgiving than validate_button_url — auto-normalizes the
    @username and bare t.me/x shorthand admins naturally type for a
    channel link, since that's specifically what this validates (unlike
    generic custom buttons, which could point anywhere). Extracted from
    the old single-link zero-result flow, unchanged, so backup channel
    links keep the exact input handling that already worked."""
    text = raw.strip()
    if text.startswith("@"):
        url = f"https://t.me/{text[1:]}"
    elif text.startswith(("t.me/", "telegram.me/")):
        url = f"https://{text}"
    else:
        url = text
    return url if url.startswith(("http://", "https://")) else None


# ── Top-level menu ───────────────────────────────────────────────────────────

@router.message(F.text == "🔘 Delivery Buttons")
async def delivery_buttons_home(message: Message) -> None:
    await message.answer(
        "🔘 <b>Delivery Buttons</b>\n\n"
        "Manage the buttons shown on delivered files and zero-result searches.",
        reply_markup=delivery_buttons_menu_keyboard(),
    )


@router.callback_query(F.data == "delbtn:menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(
        "🔘 <b>Delivery Buttons</b>\n\n"
        "Manage the buttons shown on delivered files and zero-result searches.",
        reply_markup=delivery_buttons_menu_keyboard(),
    )
    await callback.answer()


# ── Default buttons (Watch Later, Report Broken Link, Request Movie,
# Check Backup Channel) — rename + on/off only, function stays fixed ───────

@router.callback_query(F.data == "delbtn:defaults")
async def show_default_buttons(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    config = await SettingsService(session).get_default_button_config()
    await callback.message.edit_text(
        "🔘 <b>Default Buttons</b>\n\nTap one to edit its label(s) or turn it on/off.",
        reply_markup=default_buttons_list_keyboard(config),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("delbtn:default:manage:"))
async def manage_default_button(callback: CallbackQuery, session: AsyncSession) -> None:
    slot = callback.data.split(":")[3]
    config = await SettingsService(session).get_default_button_config()
    slot_state = config.get(slot)
    if not slot_state:
        await callback.answer("Unknown button slot.", show_alert=True)
        return
    label_am = slot_state.get("label_am")
    label_am_shown = f"<b>{_escape_html(label_am)}</b>" if label_am else "<i>not set — falls back to English</i>"
    await callback.message.edit_text(
        f"<b>{SLOT_TITLES[slot]}</b>\n\n"
        f"🇬🇧 {_escape_html(slot_state['label'])}\n"
        f"🇪🇹 {label_am_shown}\n\n"
        f"Status: {'🟢 On' if slot_state['enabled'] else '🔴 Off'}",
        reply_markup=default_button_manage_keyboard(slot, slot_state["enabled"], bool(label_am)),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("delbtn:default:toggle:"))
async def toggle_default_button(callback: CallbackQuery, session: AsyncSession) -> None:
    slot = callback.data.split(":")[3]
    new_state = await SettingsService(session).toggle_default_button(slot)
    if new_state is None:
        await callback.answer("Unknown button slot.", show_alert=True)
        return
    await callback.answer(f"{SLOT_TITLES[slot]}: {'ON' if new_state else 'OFF'}")
    await manage_default_button(callback, session)


@router.callback_query(F.data.startswith("delbtn:default:clear_label_am:"))
async def clear_default_label_am(callback: CallbackQuery, session: AsyncSession) -> None:
    slot = callback.data.split(":")[3]
    await SettingsService(session).clear_default_button_label_am(slot)
    await callback.answer("Amharic label cleared.")
    await manage_default_button(callback, session)


@router.callback_query(F.data.startswith("delbtn:default:edit_label:"))
async def edit_default_label_start(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, _, lang, slot = callback.data.split(":")
    await state.update_data(slot_to_edit=slot, label_lang=lang)
    await state.set_state(DeliveryButtonStates.renaming_default_slot)
    lang_name = "English" if lang == "en" else "Amharic"
    await callback.message.edit_text(f"Send the new {lang_name} label for <b>{SLOT_TITLES[slot]}</b>:")
    await callback.answer()


@router.message(DeliveryButtonStates.renaming_default_slot)
async def edit_default_label_apply(message: Message, session: AsyncSession, state: FSMContext) -> None:
    label = (message.text or "").strip()
    if not label:
        await message.answer("❌ Send some text for the label.")
        return
    if len(label) > 64:
        await message.answer("❌ Keep it under 64 characters.")
        return

    data = await state.get_data()
    slot = data["slot_to_edit"]
    lang = data.get("label_lang", "en")
    await SettingsService(session).set_default_button_label(slot, lang, label)
    await state.clear()
    await message.answer(f"✅ {'English' if lang == 'en' else 'Amharic'} label updated to <b>{_escape_html(label)}</b>.")


# ── Custom buttons on every delivered file ──────────────────────────────────

async def _render_custom_list(session: AsyncSession, text_target, *, edit: bool) -> None:
    buttons = await SettingsService(session).get_movie_delivery_buttons()
    text = f"🔗 <b>Custom File Buttons</b> ({len(buttons)} total)\n\nShown on every delivered movie file."
    markup = custom_buttons_list_keyboard(buttons)
    if edit:
        await text_target.edit_text(text, reply_markup=markup)
    else:
        await text_target.answer(text, reply_markup=markup)


@router.callback_query(F.data == "delbtn:custom:list")
async def custom_list(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    await _render_custom_list(session, callback.message, edit=True)
    await callback.answer()


@router.callback_query(F.data == "delbtn:custom:add")
async def custom_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(label_lang="en")
    await state.set_state(DeliveryButtonStates.entering_custom_label)
    await callback.message.edit_text(
        "Step 1/2 — Send the button's label:\n\n"
        "You can add an Amharic version afterward from this button's manage screen."
    )
    await callback.answer()


@router.message(DeliveryButtonStates.entering_custom_label)
async def custom_label_input(message: Message, session: AsyncSession, state: FSMContext) -> None:
    label = (message.text or "").strip()
    if not label:
        await message.answer("❌ Send some text for the label.")
        return
    if len(label) > 64:
        await message.answer("❌ Keep it under 64 characters.")
        return

    data = await state.get_data()
    lang = data.get("label_lang", "en")

    if data.get("custom_id_to_edit"):
        field = "label" if lang == "en" else "label_am"
        await SettingsService(session).update_movie_delivery_button(data["custom_id_to_edit"], **{field: label})
        await state.clear()
        await message.answer(f"✅ {'English' if lang == 'en' else 'Amharic'} label updated.")
        return

    await state.update_data(label=label)
    await state.set_state(DeliveryButtonStates.entering_custom_url)
    await message.answer("Step 2/2 — Send the URL (must start with https://):")


@router.callback_query(F.data.startswith("delbtn:custom:edit_url:"))
async def custom_edit_url_start(callback: CallbackQuery, state: FSMContext) -> None:
    btn_id = int(callback.data.split(":")[3])
    await state.update_data(custom_id_to_edit=btn_id)
    await state.set_state(DeliveryButtonStates.entering_custom_url)
    await callback.message.edit_text("Send the new URL (must start with https://):")
    await callback.answer()


@router.message(DeliveryButtonStates.entering_custom_url)
async def custom_url_input(message: Message, session: AsyncSession, state: FSMContext) -> None:
    url = validate_button_url(message.text or "")
    if not url:
        await message.answer("❌ The URL must start with https:// (or http:// / tg://) and be under 512 characters. Try again:")
        return

    data = await state.get_data()
    settings_svc = SettingsService(session)
    if data.get("custom_id_to_edit"):
        await settings_svc.update_movie_delivery_button(data["custom_id_to_edit"], url=url)
        await state.clear()
        await message.answer("✅ URL updated.")
        return

    await settings_svc.add_movie_delivery_button(label=data["label"], url=url)
    await state.clear()
    await message.answer(f"✅ Button <b>{_escape_html(data['label'])}</b> added — it'll show on every delivered file.")


@router.callback_query(F.data.startswith("delbtn:custom:clear_label_am:"))
async def custom_clear_label_am(callback: CallbackQuery, session: AsyncSession) -> None:
    btn_id = int(callback.data.split(":")[3])
    await SettingsService(session).update_movie_delivery_button(btn_id, label_am=None)
    await callback.answer("Amharic label cleared.")
    await custom_manage(callback, session)


@router.callback_query(F.data.startswith("delbtn:custom:edit_label:"))
async def custom_edit_label_start(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, _, lang, btn_id = callback.data.split(":")
    await state.update_data(custom_id_to_edit=int(btn_id), label_lang=lang)
    await state.set_state(DeliveryButtonStates.entering_custom_label)
    lang_name = "English" if lang == "en" else "Amharic"
    await callback.message.edit_text(f"Send the new {lang_name} label:")
    await callback.answer()


@router.callback_query(F.data.startswith("delbtn:custom:manage:"))
async def custom_manage(callback: CallbackQuery, session: AsyncSession) -> None:
    btn_id = int(callback.data.split(":")[3])
    settings_svc = SettingsService(session)
    buttons = sorted(await settings_svc.get_movie_delivery_buttons(), key=lambda b: b.get("order", 0))
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
        reply_markup=custom_button_manage_keyboard(btn, is_first=(idx == 0), is_last=(idx == len(buttons) - 1)),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("delbtn:custom:toggle_vis:"))
async def custom_toggle_vis(callback: CallbackQuery, session: AsyncSession) -> None:
    btn_id = int(callback.data.split(":")[3])
    settings_svc = SettingsService(session)
    buttons = await settings_svc.get_movie_delivery_buttons()
    btn = next((b for b in buttons if b["id"] == btn_id), None)
    if btn:
        await settings_svc.update_movie_delivery_button(btn_id, is_visible=not btn.get("is_visible", True))
        await callback.answer("Visibility updated.")
    await custom_manage(callback, session)


@router.callback_query(F.data.startswith("delbtn:custom:move:"))
async def custom_move(callback: CallbackQuery, session: AsyncSession) -> None:
    parts = callback.data.split(":")
    btn_id, direction = int(parts[3]), (-1 if parts[4] == "up" else 1)
    await SettingsService(session).move_movie_delivery_button(btn_id, direction)
    await callback.answer()
    await custom_manage(callback, session)


@router.callback_query(F.data.startswith("delbtn:custom:delete:"))
async def custom_delete(callback: CallbackQuery, session: AsyncSession) -> None:
    btn_id = int(callback.data.split(":")[3])
    deleted = await SettingsService(session).delete_movie_delivery_button(btn_id)
    await callback.answer("✅ Deleted." if deleted else "❌ Not found.", show_alert=True)
    await _render_custom_list(session, callback.message, edit=True)


# ── Backup channel links ─────────────────────────────────────────────────────

async def _render_backup_list(session: AsyncSession, text_target, *, edit: bool) -> None:
    links = await SettingsService(session).get_backup_channel_links()
    text = f"🔗 <b>Backup Channel Links</b> ({len(links)} total)\n\nShown when a search returns nothing."
    markup = backup_links_list_keyboard(links)
    if edit:
        await text_target.edit_text(text, reply_markup=markup)
    else:
        await text_target.answer(text, reply_markup=markup)


@router.callback_query(F.data == "delbtn:backup:list")
async def backup_list(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    await _render_backup_list(session, callback.message, edit=True)
    await callback.answer()


@router.callback_query(F.data == "delbtn:backup:add")
async def backup_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(label_lang="en")
    await state.set_state(DeliveryButtonStates.entering_backup_label)
    await callback.message.edit_text(
        "Step 1/2 — Send this link's label (e.g. 🔗 Backup Channel 2):\n\n"
        "You can add an Amharic version afterward from this link's manage screen."
    )
    await callback.answer()


@router.message(DeliveryButtonStates.entering_backup_label)
async def backup_label_input(message: Message, session: AsyncSession, state: FSMContext) -> None:
    label = (message.text or "").strip()
    if not label:
        await message.answer("❌ Send some text for the label.")
        return
    if len(label) > 64:
        await message.answer("❌ Keep it under 64 characters.")
        return

    data = await state.get_data()
    lang = data.get("label_lang", "en")

    if data.get("backup_id_to_edit"):
        field = "label" if lang == "en" else "label_am"
        await SettingsService(session).update_backup_channel_link(data["backup_id_to_edit"], **{field: label})
        await state.clear()
        await message.answer(f"✅ {'English' if lang == 'en' else 'Amharic'} label updated.")
        return

    await state.update_data(label=label)
    await state.set_state(DeliveryButtonStates.entering_backup_url)
    await message.answer("Step 2/2 — Send the channel URL or @username:")


@router.callback_query(F.data.startswith("delbtn:backup:edit_url:"))
async def backup_edit_url_start(callback: CallbackQuery, state: FSMContext) -> None:
    link_id = int(callback.data.split(":")[3])
    await state.update_data(backup_id_to_edit=link_id)
    await state.set_state(DeliveryButtonStates.entering_backup_url)
    await callback.message.edit_text("Send the new channel URL or @username:")
    await callback.answer()


@router.message(DeliveryButtonStates.entering_backup_url)
async def backup_url_input(message: Message, session: AsyncSession, state: FSMContext) -> None:
    url = normalize_channel_url(message.text or "")
    if not url:
        await message.answer(
            "❌ That doesn't look like a valid link. Send a full URL "
            "(e.g. https://t.me/yourchannel) or an @username."
        )
        return

    data = await state.get_data()
    settings_svc = SettingsService(session)
    if data.get("backup_id_to_edit"):
        await settings_svc.update_backup_channel_link(data["backup_id_to_edit"], url=url)
        await state.clear()
        await message.answer(f"✅ Link updated to: {_escape_html(url)}")
        return

    await settings_svc.add_backup_channel_link(label=data["label"], url=url)
    await state.clear()
    await message.answer(f"✅ Backup link <b>{_escape_html(data['label'])}</b> added: {_escape_html(url)}")


@router.callback_query(F.data.startswith("delbtn:backup:clear_label_am:"))
async def backup_clear_label_am(callback: CallbackQuery, session: AsyncSession) -> None:
    link_id = int(callback.data.split(":")[3])
    await SettingsService(session).update_backup_channel_link(link_id, label_am=None)
    await callback.answer("Amharic label cleared.")
    await backup_manage(callback, session)


@router.callback_query(F.data.startswith("delbtn:backup:edit_label:"))
async def backup_edit_label_start(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, _, lang, link_id = callback.data.split(":")
    await state.update_data(backup_id_to_edit=int(link_id), label_lang=lang)
    await state.set_state(DeliveryButtonStates.entering_backup_label)
    lang_name = "English" if lang == "en" else "Amharic"
    await callback.message.edit_text(f"Send the new {lang_name} label:")
    await callback.answer()


@router.callback_query(F.data.startswith("delbtn:backup:manage:"))
async def backup_manage(callback: CallbackQuery, session: AsyncSession) -> None:
    link_id = int(callback.data.split(":")[3])
    settings_svc = SettingsService(session)
    links = sorted(await settings_svc.get_backup_channel_links(), key=lambda l: l.get("order", 0))
    link = next((l for l in links if l["id"] == link_id), None)
    if not link:
        await callback.answer("Link not found.", show_alert=True)
        return
    idx = links.index(link)
    label_am = link.get("label_am")
    label_am_shown = f"<b>{_escape_html(label_am)}</b>" if label_am else "<i>not set — falls back to English</i>"
    await callback.message.edit_text(
        f"🇬🇧 <b>{_escape_html(link['label'])}</b>\n"
        f"🇪🇹 {label_am_shown}\n"
        f"URL: {_escape_html(link['url'])}\n"
        f"Visible: {'🟢 Yes' if link.get('is_visible', True) else '🔴 Hidden'}",
        reply_markup=backup_link_manage_keyboard(link, is_first=(idx == 0), is_last=(idx == len(links) - 1)),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("delbtn:backup:toggle_vis:"))
async def backup_toggle_vis(callback: CallbackQuery, session: AsyncSession) -> None:
    link_id = int(callback.data.split(":")[3])
    settings_svc = SettingsService(session)
    links = await settings_svc.get_backup_channel_links()
    link = next((l for l in links if l["id"] == link_id), None)
    if link:
        await settings_svc.update_backup_channel_link(link_id, is_visible=not link.get("is_visible", True))
        await callback.answer("Visibility updated.")
    await backup_manage(callback, session)


@router.callback_query(F.data.startswith("delbtn:backup:move:"))
async def backup_move(callback: CallbackQuery, session: AsyncSession) -> None:
    parts = callback.data.split(":")
    link_id, direction = int(parts[3]), (-1 if parts[4] == "up" else 1)
    await SettingsService(session).move_backup_channel_link(link_id, direction)
    await callback.answer()
    await backup_manage(callback, session)


@router.callback_query(F.data.startswith("delbtn:backup:delete:"))
async def backup_delete(callback: CallbackQuery, session: AsyncSession) -> None:
    link_id = int(callback.data.split(":")[3])
    deleted = await SettingsService(session).delete_backup_channel_link(link_id)
    await callback.answer("✅ Deleted." if deleted else "❌ Not found.", show_alert=True)
    await _render_backup_list(session, callback.message, edit=True)
