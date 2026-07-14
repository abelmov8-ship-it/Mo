from __future__ import annotations

from html import escape as _escape_html

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.database.models.menu_button import MenuButtonAction, MenuButtonType
from bot.filters.is_admin import IsAdmin
from bot.fsm.admin import MenuWizardStates
from bot.keyboards.admin.menu import (
    ACTION_LABELS,
    action_picker_keyboard,
    keyboard_type_picker,
    menu_list_keyboard,
    menu_manage_keyboard,
)
from bot.services.menu_service import MenuButtonService

router = Router(name="admin:menu")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


async def _render_list(session, text_target, *, edit: bool) -> None:
    buttons = await MenuButtonService(session).get_all()
    text = f"🔗 <b>Main Menu Buttons</b> ({len(buttons)} total)\n\nTap a button to manage it."
    markup = menu_list_keyboard(buttons)
    if edit:
        await text_target.edit_text(text, reply_markup=markup)
    else:
        await text_target.answer(text, reply_markup=markup)


@router.message(F.text == "🔗 Menu Builder")
async def menu_builder_home(message: Message, session) -> None:
    await _render_list(session, message, edit=False)


@router.callback_query(F.data == "menuadm:list")
async def back_to_list(callback: CallbackQuery, session, state: FSMContext) -> None:
    await state.clear()
    await _render_list(session, callback.message, edit=True)
    await callback.answer()


# ── Add button wizard ───────────────────────────────────────────────────────

@router.callback_query(F.data == "menuadm:add")
async def wizard_step1_action(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_text(
        "Step 1/3 — What should this button open?", reply_markup=action_picker_keyboard()
    )
    await state.set_state(MenuWizardStates.selecting_action)
    await callback.answer()


@router.callback_query(F.data.startswith("menuadm:wiz:action:"), MenuWizardStates.selecting_action)
async def wizard_step2_type(callback: CallbackQuery, state: FSMContext) -> None:
    action = callback.data.split(":")[3]
    await state.update_data(action=action)
    await callback.message.edit_text(
        "Step 2/3 — Reply keyboard (persistent, bottom of screen) or "
        "inline keyboard (attached to the welcome message)?",
        reply_markup=keyboard_type_picker(),
    )
    await state.set_state(MenuWizardStates.selecting_keyboard_type)
    await callback.answer()


@router.callback_query(F.data.startswith("menuadm:wiz:type:"), MenuWizardStates.selecting_keyboard_type)
async def wizard_step3_label(callback: CallbackQuery, state: FSMContext) -> None:
    kb_type = callback.data.split(":")[3]
    await state.update_data(keyboard_type=kb_type, label_lang="en")
    await state.set_state(MenuWizardStates.entering_label)
    await callback.message.edit_text(
        "Step 3/3 — Send the button's display text (e.g. 🔍 Search Movies):\n\n"
        "You can add an Amharic version afterward from this button's manage screen."
    )
    await callback.answer()


@router.message(MenuWizardStates.entering_label)
async def wizard_enter_label(message: Message, session, state: FSMContext) -> None:
    label = (message.text or "").strip()
    if not label:
        await message.answer("❌ Send some text for the button label.")
        return
    if len(label) > 64:
        await message.answer("❌ Keep it under 64 characters.")
        return

    data = await state.get_data()
    svc = MenuButtonService(session)
    lang = data.get("label_lang", "en")

    if data.get("button_id_to_edit"):
        # Standalone "Edit Label" flow reuses this same state/handler —
        # only "action" and "keyboard_type" being unset distinguish the
        # add-wizard path from here.
        field = "label" if lang == "en" else "label_am"
        await svc.update(data["button_id_to_edit"], **{field: label})
        await state.clear()
        await message.answer(f"✅ {'English' if lang == 'en' else 'Amharic'} label updated.")
        return

    await svc.add(
        label=label,
        action=MenuButtonAction(data["action"]),
        keyboard_type=MenuButtonType.REPLY if data["keyboard_type"] == "reply" else MenuButtonType.INLINE,
    )
    await state.clear()
    await message.answer(f"✅ Button <b>{_escape_html(label)}</b> added to the main menu.")


@router.callback_query(F.data == "menuadm:wiz:cancel")
async def wizard_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("❌ Cancelled.")
    await callback.answer()


# ── Manage existing button ──────────────────────────────────────────────────

@router.callback_query(F.data.startswith("menuadm:manage:"))
async def manage_button(callback: CallbackQuery, session) -> None:
    btn_id = int(callback.data.split(":")[2])
    svc = MenuButtonService(session)
    btn = await svc.get_by_id(btn_id)
    if not btn:
        await callback.answer("Button not found.", show_alert=True)
        return

    all_buttons = await svc.get_all()
    idx = next(i for i, b in enumerate(all_buttons) if b.id == btn_id)

    label_am_shown = (
        f"<b>{_escape_html(btn.label_am)}</b>" if btn.label_am else "<i>not set — falls back to English</i>"
    )
    await callback.message.edit_text(
        f"🇬🇧 <b>{_escape_html(btn.label)}</b>\n"
        f"🇪🇹 {label_am_shown}\n\n"
        f"Opens: {ACTION_LABELS.get(btn.action, btn.action.value)}\n"
        f"Type: {'📌 Reply' if btn.keyboard_type == MenuButtonType.REPLY else '💬 Inline'}\n"
        f"Visible: {'🟢 Yes' if btn.is_visible else '🔴 Hidden'}",
        reply_markup=menu_manage_keyboard(btn, is_first=(idx == 0), is_last=(idx == len(all_buttons) - 1)),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("menuadm:toggle_vis:"))
async def toggle_visibility(callback: CallbackQuery, session) -> None:
    btn_id = int(callback.data.split(":")[2])
    svc = MenuButtonService(session)
    btn = await svc.get_by_id(btn_id)
    if btn:
        await svc.update(btn_id, is_visible=not btn.is_visible)
        await callback.answer("Visibility updated.")
    await manage_button(callback, session)


@router.callback_query(F.data.startswith("menuadm:toggle_type:"))
async def toggle_keyboard_type(callback: CallbackQuery, session) -> None:
    btn_id = int(callback.data.split(":")[2])
    svc = MenuButtonService(session)
    btn = await svc.get_by_id(btn_id)
    if btn:
        new_type = MenuButtonType.INLINE if btn.keyboard_type == MenuButtonType.REPLY else MenuButtonType.REPLY
        await svc.update(btn_id, keyboard_type=new_type)
        await callback.answer("Keyboard type updated.")
    await manage_button(callback, session)


@router.callback_query(F.data.startswith("menuadm:move:"))
async def move_button(callback: CallbackQuery, session) -> None:
    parts = callback.data.split(":")
    btn_id, direction = int(parts[2]), (-1 if parts[3] == "up" else 1)
    await MenuButtonService(session).move(btn_id, direction)
    await callback.answer()
    await manage_button(callback, session)


@router.callback_query(F.data.startswith("menuadm:delete:"))
async def delete_button(callback: CallbackQuery, session) -> None:
    btn_id = int(callback.data.split(":")[2])
    deleted = await MenuButtonService(session).delete(btn_id)
    msg = "✅ Button deleted." if deleted else "❌ Button not found."
    await callback.answer(msg, show_alert=True)
    await _render_list(session, callback.message, edit=True)


@router.callback_query(F.data.startswith("menuadm:clear_label_am:"))
async def clear_label_am(callback: CallbackQuery, session) -> None:
    btn_id = int(callback.data.split(":")[2])
    await MenuButtonService(session).update(btn_id, label_am=None)
    await callback.answer("Amharic label cleared.")
    await manage_button(callback, session)


@router.callback_query(F.data.startswith("menuadm:edit_label:"))
async def edit_label_start(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, lang, btn_id = callback.data.split(":")
    await state.update_data(button_id_to_edit=int(btn_id), label_lang=lang)
    await state.set_state(MenuWizardStates.entering_label)
    lang_name = "English" if lang == "en" else "Amharic"
    await callback.message.edit_text(f"Send the new {lang_name} button text:")
    await callback.answer()
