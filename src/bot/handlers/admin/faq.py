from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.filters.is_admin import IsAdmin
from bot.fsm.admin import FaqStates
from bot.keyboards.admin.faq import faq_list_keyboard, faq_manage_keyboard
from bot.services.settings_service import SettingsService

router = Router(name="admin:faq")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

_MAX_LEN = 512  # generous for a chat bubble; keeps one entry from swallowing the whole FAQ screen


async def _render_list(session, text_target, *, edit: bool) -> None:
    entries = await SettingsService(session).get_faq()
    text = f"❓ <b>FAQ</b> ({len(entries)} total)\n\nTap an entry to manage it."
    markup = faq_list_keyboard(entries)
    if edit:
        await text_target.edit_text(text, reply_markup=markup)
    else:
        await text_target.answer(text, reply_markup=markup)


@router.callback_query(F.data == "bc:manage_faq")
async def open_faq_admin(callback: CallbackQuery, session) -> None:
    await _render_list(session, callback.message, edit=True)
    await callback.answer()


@router.callback_query(F.data == "faqadm:list")
async def back_to_list(callback: CallbackQuery, session, state: FSMContext) -> None:
    await state.clear()
    await _render_list(session, callback.message, edit=True)
    await callback.answer()


# ── Add wizard (2 steps: question, then answer) ─────────────────────────────

@router.callback_query(F.data == "faqadm:add")
async def wizard_step1_question(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(FaqStates.entering_question)
    await callback.message.edit_text("Step 1/2 — Send the question:")
    await callback.answer()


@router.message(FaqStates.entering_question)
async def handle_question_input(message: Message, session, state: FSMContext) -> None:
    question = (message.text or "").strip()
    if not question:
        await message.answer("❌ Send some text for the question.")
        return
    if len(question) > _MAX_LEN:
        await message.answer(f"❌ Keep it under {_MAX_LEN} characters.")
        return

    data = await state.get_data()
    if data.get("entry_id_to_edit"):
        await SettingsService(session).update_faq_entry(data["entry_id_to_edit"], question=question)
        await state.clear()
        await message.answer("✅ Question updated.")
        return

    await state.update_data(question=question)
    await state.set_state(FaqStates.entering_answer)
    await message.answer("Step 2/2 — Send the answer:")


@router.callback_query(F.data.startswith("faqadm:edit_a:"))
async def edit_answer_start(callback: CallbackQuery, state: FSMContext) -> None:
    entry_id = int(callback.data.split(":")[2])
    await state.update_data(entry_id_to_edit=entry_id)
    await state.set_state(FaqStates.entering_answer)
    await callback.message.edit_text("Send the new answer:")
    await callback.answer()


@router.message(FaqStates.entering_answer)
async def handle_answer_input(message: Message, session, state: FSMContext) -> None:
    answer = (message.text or "").strip()
    if not answer:
        await message.answer("❌ Send some text for the answer.")
        return
    if len(answer) > _MAX_LEN:
        await message.answer(f"❌ Keep it under {_MAX_LEN} characters.")
        return

    data = await state.get_data()
    svc = SettingsService(session)

    if data.get("entry_id_to_edit"):
        await svc.update_faq_entry(data["entry_id_to_edit"], answer=answer)
        await state.clear()
        await message.answer("✅ Answer updated.")
        return

    await svc.add_faq_entry(question=data["question"], answer=answer)
    await state.clear()
    await message.answer("✅ FAQ entry added.")


@router.callback_query(F.data.startswith("faqadm:edit_q:"))
async def edit_question_start(callback: CallbackQuery, state: FSMContext) -> None:
    entry_id = int(callback.data.split(":")[2])
    await state.update_data(entry_id_to_edit=entry_id)
    await state.set_state(FaqStates.entering_question)
    await callback.message.edit_text("Send the new question:")
    await callback.answer()


# ── Manage existing entry ────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("faqadm:manage:"))
async def manage_entry(callback: CallbackQuery, session) -> None:
    entry_id = int(callback.data.split(":")[2])
    entries = sorted(await SettingsService(session).get_faq(), key=lambda e: e.get("order", 0))
    entry = next((e for e in entries if e["id"] == entry_id), None)
    if not entry:
        await callback.answer("Entry not found.", show_alert=True)
        return

    idx = entries.index(entry)
    await callback.message.edit_text(
        f"<b>{entry['question']}</b>\n\n{entry['answer']}\n\n"
        f"Visible: {'🟢 Yes' if entry.get('is_visible', True) else '🔴 Hidden'}",
        reply_markup=faq_manage_keyboard(entry, is_first=(idx == 0), is_last=(idx == len(entries) - 1)),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("faqadm:toggle_vis:"))
async def toggle_visibility(callback: CallbackQuery, session) -> None:
    entry_id = int(callback.data.split(":")[2])
    svc = SettingsService(session)
    entries = await svc.get_faq()
    entry = next((e for e in entries if e["id"] == entry_id), None)
    if entry:
        await svc.update_faq_entry(entry_id, is_visible=not entry.get("is_visible", True))
        await callback.answer("Visibility updated.")
    await manage_entry(callback, session)


@router.callback_query(F.data.startswith("faqadm:move:"))
async def move_entry(callback: CallbackQuery, session) -> None:
    parts = callback.data.split(":")
    entry_id, direction = int(parts[2]), (-1 if parts[3] == "up" else 1)
    await SettingsService(session).move_faq_entry(entry_id, direction)
    await callback.answer()
    await manage_entry(callback, session)


@router.callback_query(F.data.startswith("faqadm:delete:"))
async def delete_entry(callback: CallbackQuery, session) -> None:
    entry_id = int(callback.data.split(":")[2])
    deleted = await SettingsService(session).delete_faq_entry(entry_id)
    msg = "✅ Entry deleted." if deleted else "❌ Entry not found."
    await callback.answer(msg, show_alert=True)
    await _render_list(session, callback.message, edit=True)
