from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.filters.is_admin import IsAdmin
from bot.fsm.admin import BroadcastStates
from bot.services.broadcast_service import BroadcastService
from bot.services.user_service import UserService

router = Router(name="admin:broadcast")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


@router.message(F.text == "📢 Broadcast")
async def broadcast_menu(message: Message) -> None:
    await message.answer("📢 <b>Broadcast</b>", reply_markup=_broadcast_menu_keyboard())


def _broadcast_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="👥 Broadcast to All",     callback_data="bc:audience:all")
    builder.button(text="💎 Broadcast to VIP Only", callback_data="bc:audience:vip")
    builder.button(text="📝 Bot Texts (EN/AM)",     callback_data="txtadm:cats")
    builder.button(text="🔗 Manage Welcome Buttons", callback_data="bc:manage_welcome_buttons")
    builder.button(text="❓ Manage FAQ", callback_data="bc:manage_faq")
    builder.adjust(1)
    return builder.as_markup()


@router.callback_query(F.data == "bc:menu")
async def back_to_broadcast_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("📢 <b>Broadcast</b>", reply_markup=_broadcast_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("bc:audience:"))
async def set_audience(callback: CallbackQuery, state: FSMContext) -> None:
    audience = callback.data.split(":")[2]
    await state.update_data(audience=audience)
    await state.set_state(BroadcastStates.composing_content)
    await callback.message.edit_text(
        f"Audience: <b>{'All users' if audience == 'all' else 'VIP only'}</b>\n\n"
        "Send the broadcast content (text, photo, or video):"
    )
    await callback.answer()


@router.message(
    F.text | F.photo | F.video,
    BroadcastStates.composing_content,
)
async def handle_broadcast_content(message: Message, state: FSMContext) -> None:
    photo_id = message.photo[-1].file_id if message.photo else None
    video_id = message.video.file_id if message.video else None
    text = message.caption or message.text or ""

    await state.update_data(text=text, photo_id=photo_id, video_id=video_id)
    await state.set_state(BroadcastStates.confirming)

    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Send Now",   callback_data="bc:confirm")
    builder.button(text="❌ Cancel",     callback_data="bc:cancel")
    builder.adjust(2)
    await message.answer(
        f"📤 Ready to broadcast:\n\n<i>{text[:200] or '[Media only]'}</i>",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data == "bc:confirm", BroadcastStates.confirming)
async def confirm_broadcast(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot) -> None:
    data = await state.get_data()
    audience = data.get("audience", "all")

    user_svc = UserService(session)
    users = await user_svc.get_all_vip() if audience == "vip" else await user_svc.get_all_active()

    await callback.message.edit_text(f"⏳ Sending to {len(users):,} users…")
    await state.clear()

    bc_svc = BroadcastService(bot)
    result = await bc_svc.send_to_users(
        users=users,
        text=data.get("text", ""),
        photo_file_id=data.get("photo_id"),
        video_file_id=data.get("video_id"),
    )
    await callback.message.answer(
        f"✅ <b>Broadcast complete</b>\n\n"
        f"✔ Sent: {result.sent:,}\n"
        f"✖ Failed: {result.failed:,}\n"
        f"🚫 Blocked: {result.blocked:,}"
    )
    await callback.answer()


@router.callback_query(F.data == "bc:cancel")
async def cancel_broadcast(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("❌ Broadcast cancelled.")
    await callback.answer()
