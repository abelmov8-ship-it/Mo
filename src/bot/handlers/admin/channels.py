from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models.channel import ChannelCategory
from bot.filters.is_admin import IsAdmin
from bot.fsm.admin import ChannelWizardStates
from bot.keyboards.admin.channels import (
    channel_manage_keyboard,
    channels_list_keyboard,
    wizard_step1_keyboard,
    wizard_step2_keyboard,
)
from bot.services.channel_service import ChannelService

router = Router(name="admin:channels")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


@router.message(F.text == "🎬 Channels")
async def channels_menu(message: Message, session: AsyncSession) -> None:
    channels = await ChannelService(session).get_all()
    await message.answer(
        f"🎬 <b>Channels</b> ({len(channels)} total)", reply_markup=channels_list_keyboard(channels)
    )


@router.callback_query(F.data == "ch:list")
async def back_to_list(callback: CallbackQuery, session: AsyncSession) -> None:
    channels = await ChannelService(session).get_all()
    await callback.message.edit_text(
        f"🎬 <b>Channels</b> ({len(channels)} total)", reply_markup=channels_list_keyboard(channels)
    )
    await callback.answer()


# ── Add channel wizard ────────────────────────────────────────────────────────

@router.callback_query(F.data == "ch:add")
async def wizard_step1_category(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_text("Step 1/4 — Select category:", reply_markup=wizard_step1_keyboard())
    await state.set_state(ChannelWizardStates.selecting_category)
    await callback.answer()


@router.callback_query(F.data.startswith("ch:wiz:cat:"), ChannelWizardStates.selecting_category)
async def wizard_step2_status(callback: CallbackQuery, state: FSMContext) -> None:
    cat = callback.data.split(":")[3]
    await state.update_data(category=cat)
    await callback.message.edit_text("Step 2/4 — Force Join setting:", reply_markup=wizard_step2_keyboard())
    await state.set_state(ChannelWizardStates.selecting_status)
    await callback.answer()


@router.callback_query(F.data.startswith("ch:wiz:fj:"), ChannelWizardStates.selecting_status)
async def wizard_step3_name(callback: CallbackQuery, state: FSMContext) -> None:
    fj = callback.data.split(":")[3] == "on"
    await state.update_data(force_join=fj)
    await state.set_state(ChannelWizardStates.entering_name)
    await callback.message.edit_text("Step 3/4 — Send the channel display name:")
    await callback.answer()


@router.message(ChannelWizardStates.entering_name)
async def wizard_enter_name(message: Message, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    new_name = message.text.strip()

    if data.get("channel_id_to_edit") and "category" not in data:
        # Editing an existing channel's name — not step 3 of the add wizard
        await ChannelService(session).update(data["channel_id_to_edit"], name=new_name)
        await state.clear()
        await message.answer("✅ Name updated.")
        return

    await state.update_data(name=new_name)
    await state.set_state(ChannelWizardStates.entering_url)
    await message.answer("Step 4/4 — Now send the channel URL or @username:")


@router.message(ChannelWizardStates.entering_url)
async def wizard_enter_url(message: Message, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    new_url = message.text.strip()

    if data.get("channel_id_to_edit") and "category" not in data:
        # Editing an existing channel's URL — not step 4 of the add wizard
        await ChannelService(session).update(data["channel_id_to_edit"], url=new_url)
        await state.clear()
        await message.answer("✅ URL updated.")
        return

    await state.update_data(url=new_url)
    await state.set_state(ChannelWizardStates.entering_channel_id)
    skip = InlineKeyboardBuilder()
    skip.button(text="⏭ Skip for now", callback_data="ch:wiz:cid_skip")
    await message.answer(
        "Last step — forward any message <b>from</b> the channel so I can read its numeric ID "
        "(needed for Force Join checks and posting), or type the ID directly "
        "(e.g. <code>-1001234567890</code>).",
        reply_markup=skip.as_markup(),
    )


async def _create_channel_from_wizard(session: AsyncSession, data: dict, channel_id: int | None):
    ch_svc = ChannelService(session)
    cat = ChannelCategory.VIP if data["category"] == "vip" else ChannelCategory.FREE
    return await ch_svc.add(
        name=data["name"],
        url=data["url"],
        category=cat,
        channel_id=channel_id,
        force_join=data.get("force_join", False),
    )


@router.message(ChannelWizardStates.entering_channel_id, F.forward_from_chat)
async def wizard_enter_channel_id_forward(message: Message, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    if data.get("editing_channel_id"):
        await ChannelService(session).update(data["channel_id_to_edit"], channel_id=message.forward_from_chat.id)
        await state.clear()
        await message.answer(f"✅ Channel ID set to <code>{message.forward_from_chat.id}</code>.")
        return

    ch = await _create_channel_from_wizard(session, data, message.forward_from_chat.id)
    await state.clear()
    await message.answer(
        f"✅ Channel <b>{ch.name}</b> added successfully!\n"
        f"Category: {ch.category.value} | Force Join: {'ON' if ch.force_join else 'OFF'} | "
        f"ID: <code>{ch.channel_id}</code>"
    )


@router.message(ChannelWizardStates.entering_channel_id, F.text.regexp(r"^-?\d+$"))
async def wizard_enter_channel_id_typed(message: Message, session: AsyncSession, state: FSMContext) -> None:
    channel_id = int(message.text.strip())
    data = await state.get_data()
    if data.get("editing_channel_id"):
        await ChannelService(session).update(data["channel_id_to_edit"], channel_id=channel_id)
        await state.clear()
        await message.answer(f"✅ Channel ID set to <code>{channel_id}</code>.")
        return

    ch = await _create_channel_from_wizard(session, data, channel_id)
    await state.clear()
    await message.answer(
        f"✅ Channel <b>{ch.name}</b> added successfully!\n"
        f"Category: {ch.category.value} | Force Join: {'ON' if ch.force_join else 'OFF'} | "
        f"ID: <code>{ch.channel_id}</code>"
    )


@router.message(ChannelWizardStates.entering_channel_id)
async def wizard_enter_channel_id_invalid(message: Message) -> None:
    await message.answer(
        "❌ Forward a message from the channel, or send its numeric ID (e.g. -1001234567890)."
    )


@router.callback_query(F.data == "ch:wiz:cid_skip", ChannelWizardStates.entering_channel_id)
async def wizard_skip_channel_id(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    if data.get("editing_channel_id"):
        await state.clear()
        await callback.message.edit_text("Cancelled — channel ID unchanged.")
        await callback.answer()
        return

    ch = await _create_channel_from_wizard(session, data, None)
    await state.clear()
    await callback.message.edit_text(
        f"✅ Channel <b>{ch.name}</b> added — but without a numeric ID, Force Join checks "
        "and posting won't work for it yet. Set it later from the channel's manage menu."
    )
    await callback.answer()


@router.callback_query(F.data == "ch:wiz:cancel")
async def wizard_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("❌ Channel wizard cancelled.")
    await callback.answer()


# ── Manage existing channel ───────────────────────────────────────────────────

@router.callback_query(F.data.startswith("ch:manage:"))
async def manage_channel(callback: CallbackQuery, session: AsyncSession) -> None:
    ch_id = int(callback.data.split(":")[2])
    ch = await ChannelService(session).get_by_id(ch_id)
    if not ch:
        await callback.answer("Channel not found.", show_alert=True)
        return

    cid_line = f"<code>{ch.channel_id}</code>" if ch.channel_id else "⚠️ <i>not set — Force Join/posting disabled</i>"
    await callback.message.edit_text(
        f"<b>{ch.name}</b>\nURL: {ch.url}\nCategory: {ch.category.value}\n"
        f"Force Join: {'ON' if ch.force_join else 'OFF'}\nChannel ID: {cid_line}",
        reply_markup=channel_manage_keyboard(ch),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ch:toggle_fj:"))
async def toggle_force_join(callback: CallbackQuery, session: AsyncSession) -> None:
    ch_id = int(callback.data.split(":")[2])
    ch_svc = ChannelService(session)
    ch = await ch_svc.get_by_id(ch_id)
    if ch:
        await ch_svc.set_force_join(ch_id, not ch.force_join)
        status = "ON" if not ch.force_join else "OFF"
        await callback.answer(f"Force Join set to {status}.", show_alert=True)


@router.callback_query(F.data.startswith("ch:toggle_trending:"))
async def toggle_trending_source(callback: CallbackQuery, session: AsyncSession) -> None:
    ch_id = int(callback.data.split(":")[2])
    ch_svc = ChannelService(session)
    ch = await ch_svc.get_by_id(ch_id)
    if ch:
        await ch_svc.update(ch_id, is_trending_source=not ch.is_trending_source)
        status = "added as a" if not ch.is_trending_source else "removed as a"
        await callback.answer(f"Channel {status} Trending & New source.", show_alert=True)


@router.callback_query(F.data.startswith("ch:toggle_autoindex:"))
async def toggle_auto_index_source(callback: CallbackQuery, session: AsyncSession) -> None:
    ch_id = int(callback.data.split(":")[2])
    ch_svc = ChannelService(session)
    ch = await ch_svc.get_by_id(ch_id)
    if not ch:
        return

    if not ch.is_auto_index_source and not ch.channel_id:
        # Turning it ON without a numeric channel_id would silently do
        # nothing — incoming channel_post updates are matched by numeric
        # chat ID, never by name/URL, so this channel could never actually
        # match. content.py already guards this same gap for Post-to-
        # Channel; this is the same class of misconfiguration.
        await callback.answer(
            "❌ This channel has no numeric Channel ID set, so auto-indexing could "
            "never actually match it. Tap 🆔 Set Channel ID first, then try again.",
            show_alert=True,
        )
        return

    await ch_svc.update(ch_id, is_auto_index_source=not ch.is_auto_index_source)
    status = "added as an" if not ch.is_auto_index_source else "removed as an"
    await callback.answer(f"Channel {status} Auto-Index source.", show_alert=True)


@router.callback_query(F.data.startswith("ch:delete:"))
async def delete_channel(callback: CallbackQuery, session: AsyncSession) -> None:
    ch_id = int(callback.data.split(":")[2])
    ch_svc = ChannelService(session)
    deleted = await ch_svc.delete(ch_id)
    msg = "✅ Channel deleted." if deleted else "❌ Channel not found."
    await callback.answer(msg, show_alert=True)
    await callback.message.edit_text(msg)


@router.callback_query(F.data.startswith("ch:edit_name:"))
async def edit_name_start(callback: CallbackQuery, state: FSMContext) -> None:
    ch_id = int(callback.data.split(":")[2])
    await state.update_data(channel_id_to_edit=ch_id)
    await state.set_state(ChannelWizardStates.entering_name)
    await callback.message.edit_text("Send the new display name:")
    await callback.answer()


@router.callback_query(F.data.startswith("ch:edit_url:"))
async def edit_url_start(callback: CallbackQuery, state: FSMContext) -> None:
    ch_id = int(callback.data.split(":")[2])
    await state.update_data(channel_id_to_edit=ch_id)
    await state.set_state(ChannelWizardStates.entering_url)
    await callback.message.edit_text("Send the new URL or @username:")
    await callback.answer()


@router.callback_query(F.data.startswith("ch:edit_cid:"))
async def edit_channel_id_start(callback: CallbackQuery, state: FSMContext) -> None:
    ch_id = int(callback.data.split(":")[2])
    await state.update_data(channel_id_to_edit=ch_id, editing_channel_id=True)
    await state.set_state(ChannelWizardStates.entering_channel_id)
    skip = InlineKeyboardBuilder()
    skip.button(text="❌ Cancel", callback_data="ch:wiz:cid_skip")
    await callback.message.edit_text(
        "Forward a message from the channel, or type its numeric ID:", reply_markup=skip.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ch:edit_price:"))
async def edit_price_start(callback: CallbackQuery, state: FSMContext) -> None:
    ch_id = int(callback.data.split(":")[2])
    await state.update_data(channel_id_to_edit=ch_id)
    await state.set_state(ChannelWizardStates.entering_custom_price)
    await callback.message.edit_text(
        "Send this channel's custom PPV price (in Birr) — any file forwarded from here "
        "will use this price instead of the global default.\n\n"
        "Send <code>clear</code> to remove the override and go back to using the global default."
    )
    await callback.answer()


@router.message(ChannelWizardStates.entering_custom_price)
async def edit_price_apply(message: Message, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    ch_id = data["channel_id_to_edit"]
    raw = message.text.strip()

    if raw.lower() in ("clear", "none", "remove"):
        await ChannelService(session).update(ch_id, custom_ppv_price=None)
        await state.clear()
        await message.answer("✅ Custom price removed — this channel now uses the global default again.")
        return

    try:
        price = float(raw)
        if price < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Send a number ≥ 0, or 'clear' to remove the override.")
        return

    await ChannelService(session).update(ch_id, custom_ppv_price=price)
    await state.clear()
    await message.answer(
        f"✅ Custom price set to {price:.0f} Birr. Every file forwarded from this channel "
        f"will use this price from now on, regardless of the global default."
    )
