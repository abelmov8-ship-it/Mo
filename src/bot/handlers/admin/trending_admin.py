from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.filters.is_admin import IsAdmin
from bot.fsm.admin import TrendingAdminStates
from bot.keyboards.admin.trending_admin import trending_list_keyboard, trending_manage_keyboard
from bot.services.channel_service import ChannelService
from bot.services.trending_poster_service import TrendingPosterService

router = Router(name="admin:trending")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


def resolve_forwarded_source_channel(message: Message, designated_channel_ids: set[int]) -> int | None:
    """Returns the DB channel_id the forward actually came from, only if
    it's one of the admin-designated sources — otherwise None. Pulled out
    as a pure function (no DB call) so the actual enforcement rule is
    unit-testable without a live Message/session: this is what makes
    "must ONLY come from a designated channel" a real, checked rule rather
    than something only enforced by the admin's own discipline."""
    if not message.forward_from_chat:
        return None
    origin_id = message.forward_from_chat.id
    return origin_id if origin_id in designated_channel_ids else None


async def _render_list(session: AsyncSession, text_target, *, edit: bool) -> None:
    posters = await TrendingPosterService(session).get_all()
    text = f"🖼 <b>Trending Posters</b> ({len(posters)} total)\n\nTap a poster to manage it."
    markup = trending_list_keyboard(posters)
    if edit:
        await text_target.edit_text(text, reply_markup=markup)
    else:
        await text_target.answer(text, reply_markup=markup)


@router.message(F.text == "🖼 Trending Posters")
async def trending_admin_home(message: Message, session: AsyncSession) -> None:
    await _render_list(session, message, edit=False)


@router.callback_query(F.data == "trendadm:list")
async def back_to_list(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    await _render_list(session, callback.message, edit=True)
    await callback.answer()


@router.callback_query(F.data == "trendadm:add")
async def add_poster_start(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    sources = await ChannelService(session).get_trending_sources()
    if not sources:
        await callback.answer(
            "No channels are designated as Trending sources yet. "
            "Go to 🎬 Channels → pick a channel → 🔥 Set as Trending Source first.",
            show_alert=True,
        )
        return

    names = ", ".join(ch.name for ch in sources)
    await state.set_state(TrendingAdminStates.awaiting_poster_forward)
    await callback.message.edit_text(
        f"Forward a photo post from one of your designated channels: <b>{names}</b>\n\n"
        "It must be an actual Telegram-forwarded message (not a re-sent copy) — "
        "that's how this gets verified as coming from an approved source."
    )
    await callback.answer()


@router.message(F.photo, TrendingAdminStates.awaiting_poster_forward)
async def add_poster_receive(message: Message, session: AsyncSession, state: FSMContext) -> None:
    sources = await ChannelService(session).get_trending_sources()
    designated_ids = {ch.channel_id for ch in sources if ch.channel_id is not None}

    channel_id = resolve_forwarded_source_channel(message, designated_ids)
    if channel_id is None:
        await message.answer(
            "❌ That photo isn't a forward from one of your designated Trending source "
            "channels. Forward it directly from the channel itself and try again."
        )
        return

    channel = next(ch for ch in sources if ch.channel_id == channel_id)
    poster = await TrendingPosterService(session).add(
        image_file_id=message.photo[-1].file_id,
        caption=message.caption,
        source_channel_id=channel.id,
    )
    await state.clear()
    await message.answer(f"✅ Poster added to Trending & New, sourced from <b>{channel.name}</b>.")


@router.message(TrendingAdminStates.awaiting_poster_forward)
async def add_poster_wrong_type(message: Message) -> None:
    await message.answer("❌ Forward a photo post from a designated channel (not text).")


@router.callback_query(F.data.startswith("trendadm:manage:"))
async def manage_poster(callback: CallbackQuery, session: AsyncSession) -> None:
    poster_id = int(callback.data.split(":")[2])
    svc = TrendingPosterService(session)
    posters = await svc.get_all()
    poster = next((p for p in posters if p.id == poster_id), None)
    if not poster:
        await callback.answer("Poster not found.", show_alert=True)
        return

    idx = posters.index(poster)
    channel = await ChannelService(session).get_by_id(poster.source_channel_id) if poster.source_channel_id else None
    await callback.message.edit_text(
        f"Caption: {poster.caption or '(none)'}\n"
        f"Source: {channel.name if channel else '(channel removed)'}\n"
        f"Visible: {'🟢 Yes' if poster.is_visible else '🔴 Hidden'}",
        reply_markup=trending_manage_keyboard(poster, is_first=(idx == 0), is_last=(idx == len(posters) - 1)),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("trendadm:toggle_vis:"))
async def toggle_visibility(callback: CallbackQuery, session: AsyncSession) -> None:
    poster_id = int(callback.data.split(":")[2])
    svc = TrendingPosterService(session)
    poster = await svc.get_by_id(poster_id)
    if poster:
        await svc.update(poster_id, is_visible=not poster.is_visible)
        await callback.answer("Visibility updated.")
    await manage_poster(callback, session)


@router.callback_query(F.data.startswith("trendadm:move:"))
async def move_poster(callback: CallbackQuery, session: AsyncSession) -> None:
    parts = callback.data.split(":")
    poster_id, direction = int(parts[2]), (-1 if parts[3] == "up" else 1)
    await TrendingPosterService(session).move(poster_id, direction)
    await callback.answer()
    await manage_poster(callback, session)


@router.callback_query(F.data.startswith("trendadm:delete:"))
async def delete_poster(callback: CallbackQuery, session: AsyncSession) -> None:
    poster_id = int(callback.data.split(":")[2])
    deleted = await TrendingPosterService(session).delete(poster_id)
    msg = "✅ Poster deleted." if deleted else "❌ Poster not found."
    await callback.answer(msg, show_alert=True)
    await _render_list(session, callback.message, edit=True)
