from __future__ import annotations

import logging
from datetime import datetime, timezone

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.filters.is_admin import IsAdmin
from bot.fsm.admin import (
    AdminTextInputStates,
    FileManagerStates,
    PromoCodeStates,
    UserManagementStates,
)
from bot.keyboards.admin.system import (
    anti_spam_keyboard,
    delete_timer_keyboard,
    export_keyboard,
    keyboard_type_toggle_keyboard,
    maintenance_keyboard,
    promo_list_keyboard,
    promo_type_keyboard,
    system_menu_keyboard,
    user_action_keyboard,
)
from bot.database.models.promo_code import PromoCodeType
from bot.database.models.search_log import SearchLog, SearchLogKind
from bot.services.movie_service import MovieService
from bot.services.channel_service import ChannelService
from bot.database.models.channel import Channel
from bot.services.promo_service import PromoService
from bot.services.settings_service import SettingsService
from bot.services.user_service import UserService
from bot.utils.excel_exporter import export_users_to_bytes
from bot.utils.formatters import format_expiry, format_profile

router = Router(name="admin:system")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

logger = logging.getLogger(__name__)


@router.message(F.text == "⚙️ System Tools")
async def system_menu(message: Message) -> None:
    await message.answer("⚙️ <b>System Tools</b>", reply_markup=system_menu_keyboard())


# ── User Management ─────────────────────────────────────────────────────────

@router.message(F.text == "👤 Manage User")
async def manage_user_prompt(message: Message, state: FSMContext) -> None:
    await state.set_state(UserManagementStates.entering_user_id)
    await message.answer("Send the Telegram user ID:")


async def _show_user_actions(target, send) -> None:
    user_svc = UserService(target["session"])
    sub = await user_svc.get_active_subscription(target["user"])
    text = format_profile(target["user"], sub) + "\n\n<b>Admin actions:</b>"
    await send(text, reply_markup=user_action_keyboard(target["user"].id, target["user"].is_banned))


@router.message(UserManagementStates.entering_user_id)
async def handle_manage_user_id(message: Message, session: AsyncSession, state: FSMContext) -> None:
    try:
        target_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Invalid ID. Please send a numeric Telegram user ID.")
        return

    user_svc = UserService(session)
    user = await user_svc.get_by_telegram_id(target_id)
    if not user:
        await message.answer("❌ User not found.")
        await state.clear()
        return

    sub = await user_svc.get_active_subscription(user)
    text = format_profile(user, sub) + "\n\n<b>Admin actions:</b>"
    await state.clear()
    await message.answer(text, reply_markup=user_action_keyboard(user.id, user.is_banned))


@router.callback_query(F.data.startswith("admin_user:toggle_ban:"))
async def toggle_ban(callback: CallbackQuery, session: AsyncSession) -> None:
    user_id = int(callback.data.split(":")[2])
    user_svc = UserService(session)
    user = await user_svc.get_by_id(user_id)
    if not user:
        await callback.answer("User not found.", show_alert=True)
        return
    if user.is_banned:
        await user_svc.unban(user)
        await callback.answer("✅ User unbanned.", show_alert=True)
    else:
        await user_svc.ban(user)
        await callback.answer("🚫 User banned.", show_alert=True)


@router.callback_query(F.data.startswith("admin_user:grant_vip:"))
async def grant_vip_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = int(callback.data.split(":")[2])
    await state.update_data(target_user_id=user_id)
    await state.set_state(UserManagementStates.granting_vip_days)
    await callback.message.answer("➕ Send the number of VIP days to grant (e.g. 3, 4, 14):")
    await callback.answer()


@router.message(UserManagementStates.granting_vip_days)
async def grant_vip_apply(message: Message, session: AsyncSession, state: FSMContext) -> None:
    try:
        days = int(message.text.strip())
        if days <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Send a positive whole number of days.")
        return

    data = await state.get_data()
    user_svc = UserService(session)
    user = await user_svc.get_by_id(data["target_user_id"])
    if not user:
        await message.answer("❌ User no longer exists.")
        await state.clear()
        return

    sub = await user_svc.grant_vip(user, days=days)
    await state.clear()
    await message.answer(f"✅ Granted <b>{days} VIP days</b>. New expiry: {format_expiry(sub)}")
    try:
        await message.bot.send_message(
            user.telegram_id, f"🎉 An admin granted you <b>{days} VIP days</b>!"
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("admin_user:wallet:"))
async def adjust_wallet_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = int(callback.data.split(":")[2])
    await state.update_data(target_user_id=user_id)
    await state.set_state(UserManagementStates.adjusting_wallet)
    await callback.message.answer(
        "💰 Send the wallet adjustment (e.g. <code>50</code> to add, <code>-20</code> to deduct):"
    )
    await callback.answer()


@router.message(UserManagementStates.adjusting_wallet)
async def adjust_wallet_apply(message: Message, session: AsyncSession, state: FSMContext) -> None:
    try:
        delta = float(message.text.strip())
    except ValueError:
        await message.answer("❌ Send a number, e.g. 50 or -20.")
        return

    data = await state.get_data()
    user_svc = UserService(session)
    user = await user_svc.get_by_id(data["target_user_id"])
    if not user:
        await message.answer("❌ User no longer exists.")
        await state.clear()
        return

    # ponytail: clamps at zero rather than allowing a negative balance —
    # an admin "reducing" a balance below what's there has no real-world
    # meaning here. Inline rather than a new UserService method since it's
    # a 1-line admin-only operation, not logic anything else needs.
    user.wallet_balance = max(0.0, round(user.wallet_balance + delta, 2))
    await state.clear()
    await message.answer(f"✅ New balance: <b>{user.wallet_balance:.2f} Birr</b>")


# ── Promo Codes ──────────────────────────────────────────────────────────────

@router.message(F.text == "🎟️ Promo Codes")
async def promo_list(message: Message, session: AsyncSession) -> None:
    codes = await PromoService(session).list_all()
    await message.answer(
        f"🎟️ <b>Promo Codes</b> ({len(codes)} total)",
        reply_markup=promo_list_keyboard(codes),
    )


@router.callback_query(F.data == "promo:create")
async def promo_create_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(PromoCodeStates.selecting_type)
    await callback.message.edit_text("Step 1 — Select code type:", reply_markup=promo_type_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("promo:type:"), PromoCodeStates.selecting_type)
async def promo_set_type(callback: CallbackQuery, state: FSMContext) -> None:
    type_key = callback.data.split(":")[2]
    code_type = PromoCodeType.VIP_DAYS if type_key == "vip_days" else PromoCodeType.WALLET_CREDIT
    await state.update_data(code_type=code_type.value)
    await state.set_state(PromoCodeStates.entering_code)
    await callback.message.edit_text("Step 2 — Send the code string (e.g. VIP2026):")
    await callback.answer()


@router.message(PromoCodeStates.entering_code)
async def promo_set_code(message: Message, session: AsyncSession, state: FSMContext) -> None:
    code = message.text.strip().upper()
    if not code or " " in code:
        await message.answer("❌ Send a single word, no spaces.")
        return
    if await PromoService(session).get_by_code(code):
        await message.answer("❌ That code already exists. Send a different one.")
        return

    await state.update_data(code=code)
    await state.set_state(PromoCodeStates.entering_value)
    data = await state.get_data()
    unit = "VIP days" if data["code_type"] == PromoCodeType.VIP_DAYS.value else "Birr credit"
    await message.answer(f"Step 3 — Send the {unit} amount (e.g. 7):")


@router.message(PromoCodeStates.entering_value)
async def promo_set_value(message: Message, state: FSMContext) -> None:
    try:
        value = float(message.text.strip())
        if value <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Send a positive number.")
        return
    await state.update_data(value=value)
    await state.set_state(PromoCodeStates.entering_limit)
    await message.answer("Step 4 — Usage limit? Send a number, or 'skip' for unlimited:")


@router.message(PromoCodeStates.entering_limit)
async def promo_set_limit(message: Message, state: FSMContext) -> None:
    text = message.text.strip().lower()
    if text == "skip":
        limit = None
    else:
        try:
            limit = int(text)
            if limit <= 0:
                raise ValueError
        except ValueError:
            await message.answer("❌ Send a positive whole number, or 'skip'.")
            return
    await state.update_data(usage_limit=limit)
    await state.set_state(PromoCodeStates.entering_expiry)
    await message.answer("Step 5 — Expiry date? Send as YYYY-MM-DD, or 'skip' for never:")


@router.message(PromoCodeStates.entering_expiry)
async def promo_set_expiry(message: Message, session: AsyncSession, state: FSMContext) -> None:
    text = message.text.strip().lower()
    expires_at = None
    if text != "skip":
        try:
            expires_at = datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            await message.answer("❌ Use YYYY-MM-DD format, or 'skip'.")
            return

    data = await state.get_data()
    promo = await PromoService(session).create(
        code=data["code"],
        code_type=PromoCodeType(data["code_type"]),
        value=data["value"],
        usage_limit=data.get("usage_limit"),
        expires_at=expires_at,
    )
    await state.clear()
    await message.answer(
        f"✅ Promo code <b>{promo.code}</b> created!\n"
        f"Users can redeem it with <code>/redeem {promo.code}</code>"
    )


@router.callback_query(F.data.startswith("promo:view:"))
async def promo_view(callback: CallbackQuery, session: AsyncSession) -> None:
    promo_id = int(callback.data.split(":")[2])
    promo = await PromoService(session).get_by_id(promo_id)
    if not promo:
        await callback.answer("Not found.", show_alert=True)
        return

    unit = "VIP days" if promo.code_type == PromoCodeType.VIP_DAYS else "Birr"
    limit_text = "Unlimited" if promo.usage_limit is None else f"{promo.used_count}/{promo.usage_limit}"
    expiry_text = "Never" if promo.expires_at is None else promo.expires_at.strftime("%Y-%m-%d")

    builder = InlineKeyboardBuilder()
    builder.button(text="🗑️ Delete Code", callback_data=f"promo:delete:{promo.id}")
    builder.button(text="⬅️ Back", callback_data="promo:back")
    builder.adjust(1)

    await callback.message.edit_text(
        f"🎟 <b>{promo.code}</b>\n\n"
        f"Reward: {promo.value:.0f} {unit}\n"
        f"Used: {limit_text}\n"
        f"Expires: {expiry_text}",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("promo:delete:"))
async def promo_delete(callback: CallbackQuery, session: AsyncSession) -> None:
    promo_id = int(callback.data.split(":")[2])
    deleted = await PromoService(session).delete(promo_id)
    codes = await PromoService(session).list_all()
    await callback.answer("✅ Deleted." if deleted else "Not found.", show_alert=True)
    await callback.message.edit_text(
        f"🎟️ <b>Promo Codes</b> ({len(codes)} total)",
        reply_markup=promo_list_keyboard(codes),
    )


@router.callback_query(F.data.in_({"promo:back", "promo:cancel"}))
async def promo_back(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    codes = await PromoService(session).list_all()
    await callback.message.edit_text(
        f"🎟️ <b>Promo Codes</b> ({len(codes)} total)",
        reply_markup=promo_list_keyboard(codes),
    )
    await callback.answer()


# ── File Manager ─────────────────────────────────────────────────────────────

@router.message(F.text == "📂 File Manager")
async def file_manager_menu(message: Message, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    raw_price = await SettingsService(session).get("default_ppv_price")
    price_label = f"{float(raw_price):.0f} Birr" if raw_price is not None else "⚠️ Not set"

    builder = InlineKeyboardBuilder()
    builder.button(text="📥 Batch Forward Upload", callback_data="filemgr:batch_start")
    builder.button(text="🔍 Search & Edit",         callback_data="filemgr:search_start")
    builder.button(text=f"💰 Default PPV Price ({price_label})", callback_data="filemgr:default_price")
    builder.adjust(1)
    await message.answer("📂 <b>File Manager</b>", reply_markup=builder.as_markup())


@router.callback_query(F.data == "filemgr:default_price")
async def default_price_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(FileManagerStates.editing_default_price)
    await callback.message.edit_text(
        "Send the default PPV price (in Birr) to apply to every <b>new</b> batch-uploaded movie "
        "going forward.\n\nThis only affects new uploads — movies you've already added keep "
        "their current price."
    )
    await callback.answer()


@router.message(FileManagerStates.editing_default_price)
async def default_price_apply(message: Message, session: AsyncSession, state: FSMContext) -> None:
    try:
        price = float(message.text.strip())
        if price < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Send a number ≥ 0.")
        return

    await SettingsService(session).set("default_ppv_price", str(price))
    await state.clear()
    await message.answer(
        f"✅ Default PPV price set to {price:.0f} Birr. "
        f"Every new batch upload from now on will require VIP or this price — "
        f"non-VIP users will be offered wallet-PPV or VIP-upgrade instead of the free file."
    )


@router.callback_query(F.data == "filemgr:batch_start")
async def batch_upload_start(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    # No longer a hard gate here: with per-channel pricing, an admin whose
    # real source channels are all individually priced may never need a
    # global default at all. The price check now happens per file, in
    # batch_upload_receive, against whichever price actually applies to
    # that specific file's origin channel (falling back to the global
    # default only when the channel itself has no override).
    await state.set_state(FileManagerStates.awaiting_forward)
    await state.update_data(batch=[])
    await callback.message.edit_text(
        "📥 Forward movie files (video, audio, or document) here, one at a time.\n"
        "Add a caption to set the title — otherwise the filename is used.\n\n"
        "If a file's price can't be worked out (no channel-specific price and no "
        "global default), you'll be told immediately so you can fix it or skip it.\n\n"
        "Tap ✅ Finish below (or send /done) when finished."
    )
    await callback.answer()


def _resolve_media(message: Message) -> tuple[object, "MovieFileType"]:
    """Picks whichever media field is populated and reports its type. Shared
    by both ingestion points so 'what counts as a moviefile' is defined once."""
    from bot.database.models.movie import MovieFileType

    if message.video:
        return message.video, MovieFileType.VIDEO
    if message.audio:
        return message.audio, MovieFileType.AUDIO
    return message.document, MovieFileType.DOCUMENT


async def _resolve_origin_channel(session: AsyncSession, message: Message) -> Channel | None:
    """If this message was actually forwarded from a channel we have a
    record of (matched by numeric channel_id), returns that Channel row —
    regardless of is_trending_source/is_auto_index_source, since per-
    channel pricing applies to any recognized channel, not just ones
    flagged for a specific other purpose. None for a non-forward, or a
    forward from a channel we don't have a row for."""
    if not message.forward_from_chat:
        return None
    result = await session.execute(
        select(Channel).where(Channel.channel_id == message.forward_from_chat.id)
    )
    return result.scalar_one_or_none()


async def _resolve_movie_price(session: AsyncSession, channel: Channel | None) -> float | None:
    """Per-channel custom_ppv_price takes priority; falls back to the
    global default_ppv_price setting. None means neither is configured —
    callers must treat that as 'cannot index this yet', never as 'treat
    as free'. Shared by batch_upload_receive and auto_index_channel_post
    so the pricing rule can't drift between the two entry points."""
    if channel is not None and channel.custom_ppv_price is not None:
        return channel.custom_ppv_price
    raw = await SettingsService(session).get("default_ppv_price")
    return float(raw) if raw is not None else None


def _finish_batch_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Finish & Index", callback_data="filemgr:batch_finish")
    return builder.as_markup()


def _derive_title(message: Message, media, file_id: str) -> str:
    """Caption first, then the file's own name, then a last-resort
    placeholder. Shared by batch_upload_receive and the channel auto-index
    handler so title logic doesn't diverge between the two entry points."""
    title = (message.caption or getattr(media, "file_name", None) or f"Untitled {file_id[:8]}").strip()
    return title.splitlines()[0][:256]


@router.message(F.video | F.document | F.audio, FileManagerStates.awaiting_forward)
async def batch_upload_receive(message: Message, session: AsyncSession, state: FSMContext) -> None:
    media, file_type = _resolve_media(message)
    file_id = media.file_id
    title = _derive_title(message, media, file_id)

    channel = await _resolve_origin_channel(session, message)
    price = await _resolve_movie_price(session, channel)
    if price is None:
        where = f"the '{channel.name}' channel" if channel else "this file's channel"
        await message.answer(
            f"❌ Skipped <b>{title}</b> — no price is configured for {where}, and there's "
            f"no global default either. Set one of those first (💰 Set Custom Price on the "
            f"channel, or 💰 Default PPV Price in File Manager), then forward it again."
        )
        return

    data = await state.get_data()
    batch: list[dict] = data.get("batch", [])
    batch.append({"file_id": file_id, "title": title, "file_type": file_type, "ppv_price": price})
    await state.update_data(batch=batch)
    price_note = f" (from {channel.name}: {price:.0f} Birr)" if channel else f" ({price:.0f} Birr, global default)"
    await message.answer(
        f"✅ Queued ({len(batch)} so far): <b>{title}</b>{price_note}\nKeep forwarding, or finish below.",
        reply_markup=_finish_batch_keyboard(),
    )


async def _index_batch(bot: Bot, session: AsyncSession, batch: list[dict]) -> tuple[int, int]:
    """Indexes a queued batch and runs the Request Notification Engine
    against it. Returns (added_count, skipped_count). Shared by both the
    inline-button and /done text paths so there's one place this logic
    lives.

    Applies the admin-configured default_ppv_price to every entry that
    doesn't already carry its own price. batch_upload_start already refuses
    to begin a batch until this is set, so raw_price should never actually
    be None here — the 0.0 fallback is a last-resort safety net for that
    path, not a hidden default; there's still no hardcoded price shipped
    in this code, only what the admin has configured.
    """
    raw_price = await SettingsService(session).get("default_ppv_price")
    default_price = float(raw_price) if raw_price is not None else 0.0
    for entry in batch:
        entry.setdefault("ppv_price", default_price)

    movie_svc = MovieService(session)
    added = await movie_svc.batch_add(batch)
    skipped = len(batch) - len(added)

    # ponytail: case-insensitive substring match between the logged query
    # and the new title — no fuzzy matching/aliasing. Two ceilings here:
    # (1) "Avatar" won't match a request logged as "avatr" (typo) or
    # "Avatar 2009" — upgrade path is a real search-index match instead of
    # a LIKE, if misses turn out to matter. (2) titles under 4 characters
    # are skipped entirely — a title like "It" or "Up" would otherwise
    # substring-match almost any unrelated request that happens to contain
    # that word ("put it up please"), silently marking it notified and
    # making it vanish from the admin's open-requests view without ever
    # actually being fulfilled. Short titles just don't get auto-matched;
    # an admin can still resolve those requests by hand.
    from sqlalchemy import select
    for movie in added:
        if len(movie.title.strip()) < 4:
            continue
        result = await session.execute(
            select(SearchLog)
            .where(SearchLog.kind == SearchLogKind.REQUEST)
            .where(SearchLog.notified.is_(False))
            .where(SearchLog.query.ilike(f"%{movie.title}%"))
        )
        for log in result.scalars().all():
            log.notified = True
            try:
                await bot.send_message(
                    log.telegram_id,
                    f"🎬 The movie you requested is now available: <b>{movie.title}</b>! "
                    "Search for it to watch.",
                )
            except Exception:
                pass

    return len(added), skipped


@router.channel_post(F.video | F.audio | F.document)
async def auto_index_channel_post(message: Message, session: AsyncSession) -> None:
    """Fully automatic indexing for channels flagged is_auto_index_source —
    deliberately the only ingestion path that doesn't require an explicit
    admin action in the bot's own chat, since it's driven by ordinary
    channel activity instead. Two things keep it from reopening the
    free-content leak default_ppv_price was built to close: (1) it only
    fires for channels the admin has explicitly toggled on — posts in any
    other channel the bot happens to administer (force-join channels,
    Trending source channels, etc.) are ignored outright; (2) price is
    resolved via _resolve_movie_price, the same channel-first/global-
    fallback rule batch_upload_receive uses — nothing gets indexed at any
    price that wasn't actually configured somewhere. If neither this
    channel's own price nor the global default is set, nothing gets
    indexed — the admins are told why by DM instead of it silently
    defaulting to free."""
    ch_svc = ChannelService(session)
    sources = await ch_svc.get_auto_index_sources()
    channel = next((ch for ch in sources if ch.channel_id == message.chat.id), None)
    if channel is None:
        return  # not a designated source channel — not our concern

    from bot.config import settings

    price = await _resolve_movie_price(session, channel)
    if price is None:
        for admin_id in settings.ADMIN_IDS:
            try:
                await message.bot.send_message(
                    admin_id,
                    f"⚠️ A file was posted to <b>{channel.name}</b> (an Auto-Index Source), "
                    f"but it has no custom price and no global default is set either, so it "
                    f"was <b>not</b> indexed. Set one of those, then repost.",
                )
            except Exception:
                pass
        return

    media, file_type = _resolve_media(message)
    title = _derive_title(message, media, media.file_id)
    added, _skipped = await _index_batch(
        message.bot, session, [{"file_id": media.file_id, "title": title, "file_type": file_type, "ppv_price": price}]
    )

    result_text = (
        f"✅ Auto-indexed from {channel.name} ({price:.0f} Birr): <b>{title}</b>" if added
        else f"ℹ️ Already indexed (duplicate) from {channel.name}: <b>{title}</b>"
    )
    for admin_id in settings.ADMIN_IDS:
        try:
            await message.bot.send_message(admin_id, result_text)
        except Exception:
            pass


@router.callback_query(F.data == "filemgr:batch_finish")
async def batch_upload_finish_button(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    batch: list[dict] = data.get("batch", [])
    await state.clear()

    if not batch:
        await callback.message.edit_text("Nothing was forwarded — cancelled.")
        await callback.answer()
        return

    added, skipped = await _index_batch(callback.bot, session, batch)
    await callback.message.edit_text(
        f"✅ Indexed <b>{added}</b> file(s)." + (f" Skipped {skipped} duplicate(s)." if skipped else "")
    )
    await callback.answer()


@router.message(F.text == "/done", FileManagerStates.awaiting_forward)
async def batch_upload_finish(message: Message, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    batch: list[dict] = data.get("batch", [])
    await state.clear()

    if not batch:
        await message.answer("Nothing was forwarded — cancelled.")
        return

    added, skipped = await _index_batch(message.bot, session, batch)
    await message.answer(
        f"✅ Indexed <b>{added}</b> file(s)." + (f" Skipped {skipped} duplicate(s)." if skipped else "")
    )


@router.callback_query(F.data == "filemgr:search_start")
async def file_search_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(FileManagerStates.searching_file)
    cancel = InlineKeyboardBuilder()
    cancel.button(text="❌ Cancel", callback_data="filemgr:search_cancel")
    await callback.message.edit_text(
        "🔍 Send a movie ID or a title to search:", reply_markup=cancel.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data == "filemgr:search_cancel")
async def file_search_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("❌ Cancelled.")
    await callback.answer()


@router.message(FileManagerStates.searching_file)
async def file_search_results(message: Message, session: AsyncSession, state: FSMContext) -> None:
    movie_svc = MovieService(session)
    query = message.text.strip()

    movie = None
    if query.isdigit():
        movie = await movie_svc.get_by_id(int(query))
        results = [movie] if movie else []
    else:
        results = await movie_svc.search(query, limit=10)

    if not results:
        await message.answer("No matching files. Try a different search, or tap ❌ Cancel above.")
        return

    await state.clear()
    builder = InlineKeyboardBuilder()
    for m in results:
        flag = "⚠️ " if m.is_broken else ""
        builder.button(text=f"{flag}{m.title} (#{m.id})", callback_data=f"filemgr:edit:{m.id}")
    builder.adjust(1)
    await message.answer(f"Found {len(results)}:", reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("filemgr:edit:"))
async def file_edit_menu(callback: CallbackQuery, session: AsyncSession) -> None:
    movie_id = int(callback.data.split(":")[2])
    movie = await MovieService(session).get_by_id(movie_id)
    if not movie:
        await callback.answer("Not found.", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Rename",       callback_data=f"filemgr:rename:{movie_id}")
    builder.button(text="🔗 Replace File",  callback_data=f"filemgr:relink:{movie_id}")
    builder.button(text="💰 Set PPV Price", callback_data=f"filemgr:price:{movie_id}")
    builder.button(text="🗑️ Delete",       callback_data=f"filemgr:del:{movie_id}:ask")
    builder.adjust(1)
    await callback.message.edit_text(
        f"<b>{movie.title}</b>\nID: {movie.id} | Views: {movie.view_count} | "
        f"PPV: {f'{movie.ppv_price:.0f} Birr' if movie.is_ppv else 'Free'} | "
        f"{'⚠️ Broken' if movie.is_broken else '✅ OK'}",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("filemgr:price:"))
async def file_price_start(callback: CallbackQuery, state: FSMContext) -> None:
    movie_id = int(callback.data.split(":")[2])
    await state.update_data(movie_id=movie_id)
    await state.set_state(FileManagerStates.editing_price)
    await callback.message.edit_text("Send the PPV price in Birr (0 to make it free):")
    await callback.answer()


@router.message(FileManagerStates.editing_price)
async def file_price_apply(message: Message, session: AsyncSession, state: FSMContext) -> None:
    try:
        price = float(message.text.strip())
        if price < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Send a number ≥ 0.")
        return
    data = await state.get_data()
    await MovieService(session).set_ppv_price(data["movie_id"], price)
    await state.clear()
    await message.answer(
        "✅ Now free to search." if price == 0 else f"✅ PPV price set to {price:.0f} Birr."
    )


@router.callback_query(F.data.startswith("filemgr:rename:"))
async def file_rename_start(callback: CallbackQuery, state: FSMContext) -> None:
    movie_id = int(callback.data.split(":")[2])
    await state.update_data(movie_id=movie_id)
    await state.set_state(FileManagerStates.editing_title)
    await callback.message.edit_text("Send the new title:")
    await callback.answer()


@router.message(FileManagerStates.editing_title)
async def file_rename_apply(message: Message, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    await MovieService(session).update_title(data["movie_id"], message.text.strip()[:256])
    await state.clear()
    await message.answer("✅ Title updated.")


@router.callback_query(F.data.startswith("filemgr:relink:"))
async def file_relink_start(callback: CallbackQuery, state: FSMContext) -> None:
    movie_id = int(callback.data.split(":")[2])
    await state.update_data(movie_id=movie_id)
    await state.set_state(FileManagerStates.editing_link)
    await callback.message.edit_text("Forward the replacement video/audio/document:")
    await callback.answer()


@router.message(F.video | F.document | F.audio, FileManagerStates.editing_link)
async def file_relink_apply(message: Message, session: AsyncSession, state: FSMContext) -> None:
    media, file_type = _resolve_media(message)
    data = await state.get_data()
    await MovieService(session).update_file_id(data["movie_id"], media.file_id, file_type=file_type)
    await state.clear()
    await message.answer("✅ File replaced and unmarked as broken.")


@router.callback_query(F.data.regexp(r"^filemgr:del:\d+:ask$"))
async def file_delete_ask(callback: CallbackQuery) -> None:
    movie_id = int(callback.data.split(":")[2])
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Yes, delete", callback_data=f"filemgr:del:{movie_id}:yes")
    builder.button(text="❌ Cancel",      callback_data=f"filemgr:edit:{movie_id}")
    builder.adjust(2)
    await callback.message.edit_text("Delete this file permanently?", reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.regexp(r"^filemgr:del:\d+:yes$"))
async def file_delete_confirm(callback: CallbackQuery, session: AsyncSession) -> None:
    movie_id = int(callback.data.split(":")[2])
    deleted = await MovieService(session).delete(movie_id)
    await callback.answer("✅ Deleted." if deleted else "Not found.", show_alert=True)
    await callback.message.edit_text("🗑️ File removed." if deleted else "Not found.")


# ── Excel Export ─────────────────────────────────────────────────────────────

@router.message(F.text == "📊 Export Excel")
async def export_excel_prompt(message: Message) -> None:
    await message.answer("Choose export segment:", reply_markup=export_keyboard())


@router.callback_query(F.data.startswith("export:"))
async def handle_export(callback: CallbackQuery, session: AsyncSession) -> None:
    segment = callback.data.split(":")[1]
    await callback.answer("⏳ Generating export...")

    user_svc = UserService(session)
    users = await user_svc.get_all_by_segment(segment)
    raw = export_users_to_bytes(users, segment)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    filename = f"users_{segment}_{ts}.xlsx"

    await callback.message.answer_document(
        BufferedInputFile(raw, filename=filename),
        caption=f"📊 Exported <b>{len(users)}</b> users ({segment})",
    )


# ── DB Backup ────────────────────────────────────────────────────────────────

@router.message(F.text == "💾 DB Backup")
async def manual_backup(message: Message, bot: Bot) -> None:
    from bot.tasks.db_backup import send_manual_backup
    await message.answer("⏳ Creating backup...")
    ok = await send_manual_backup(bot, message.chat.id)
    if not ok:
        await message.answer("❌ Backup failed — database file not found.")


# ── Core Config ──────────────────────────────────────────────────────────────

@router.message(F.text == "🛠️ Core Config")
async def core_config_menu(message: Message) -> None:
    from bot.config import settings
    await message.answer(
        "🛠️ <b>Core Configuration</b>",
        reply_markup=maintenance_keyboard(settings.MAINTENANCE_MODE),
    )
    await message.answer(
        "⏳ <b>Delete Timer</b>\nHow long before search messages are auto-deleted:",
        reply_markup=delete_timer_keyboard(settings.DELETE_TIMER_MINUTES),
    )
    await message.answer(
        "🛡️ <b>Anti-Spam</b>\nMax clicks per second before a temporary lockout:",
        reply_markup=anti_spam_keyboard(settings.ANTI_SPAM_THRESHOLD),
    )
    builder = InlineKeyboardBuilder()
    builder.button(text="🌐 Set Support Username", callback_data="admin:set_support_username")
    await message.answer(
        f"🌐 <b>Link Settings</b>\nSupport: @{settings.SUPPORT_USERNAME or 'not set'}",
        reply_markup=builder.as_markup(),
    )
    await message.answer(
        "🎬 <b>Channels Keyboard</b>\nHow the Free/VIP Channels picker is shown to users:",
        reply_markup=keyboard_type_toggle_keyboard(settings.CHANNELS_KEYBOARD_TYPE, "admin:toggle_channels_kb"),
    )
    await message.answer(
        "💳 <b>Payment Keyboard</b>\nHow the payment method picker (Chapa/Bank/Wallet) is shown to users:",
        reply_markup=keyboard_type_toggle_keyboard(settings.PAYMENT_KEYBOARD_TYPE, "admin:toggle_payment_kb"),
    )


@router.callback_query(F.data.startswith("admin:set_timer:"))
async def set_delete_timer(callback: CallbackQuery, session: AsyncSession) -> None:
    from bot.config import settings
    minutes = int(callback.data.split(":")[2])
    settings.DELETE_TIMER_MINUTES = minutes
    await SettingsService(session).set_int("delete_timer_minutes", minutes)
    label = "Never" if minutes == 0 else f"{minutes} min"
    await callback.answer(f"✅ Delete timer set to: {label}", show_alert=True)
    await callback.message.edit_reply_markup(reply_markup=delete_timer_keyboard(minutes))


@router.callback_query(F.data == "admin:toggle_maintenance")
async def toggle_maintenance(callback: CallbackQuery, session: AsyncSession) -> None:
    from bot.config import settings
    settings.MAINTENANCE_MODE = not settings.MAINTENANCE_MODE
    await SettingsService(session).set_bool("maintenance_mode", settings.MAINTENANCE_MODE)
    status = "ON" if settings.MAINTENANCE_MODE else "OFF"
    await callback.answer(f"🛠️ Maintenance mode: {status}", show_alert=True)
    await callback.message.edit_reply_markup(
        reply_markup=maintenance_keyboard(settings.MAINTENANCE_MODE)
    )


@router.callback_query(F.data == "admin:toggle_channels_kb")
async def toggle_channels_keyboard_type(callback: CallbackQuery, session: AsyncSession) -> None:
    from bot.config import settings
    settings.CHANNELS_KEYBOARD_TYPE = "inline" if settings.CHANNELS_KEYBOARD_TYPE == "reply" else "reply"
    await SettingsService(session).set("channels_keyboard_type", settings.CHANNELS_KEYBOARD_TYPE)
    await callback.answer(f"🎬 Channels keyboard: {settings.CHANNELS_KEYBOARD_TYPE}", show_alert=True)
    await callback.message.edit_reply_markup(
        reply_markup=keyboard_type_toggle_keyboard(settings.CHANNELS_KEYBOARD_TYPE, "admin:toggle_channels_kb")
    )


@router.callback_query(F.data == "admin:toggle_payment_kb")
async def toggle_payment_keyboard_type(callback: CallbackQuery, session: AsyncSession) -> None:
    from bot.config import settings
    settings.PAYMENT_KEYBOARD_TYPE = "inline" if settings.PAYMENT_KEYBOARD_TYPE == "reply" else "reply"
    await SettingsService(session).set("payment_keyboard_type", settings.PAYMENT_KEYBOARD_TYPE)
    await callback.answer(f"💳 Payment keyboard: {settings.PAYMENT_KEYBOARD_TYPE}", show_alert=True)
    await callback.message.edit_reply_markup(
        reply_markup=keyboard_type_toggle_keyboard(settings.PAYMENT_KEYBOARD_TYPE, "admin:toggle_payment_kb")
    )


@router.callback_query(F.data.startswith("admin:set_spam_threshold:"))
async def set_spam_threshold(callback: CallbackQuery, session: AsyncSession) -> None:
    from bot.config import settings
    threshold = int(callback.data.split(":")[2])
    settings.ANTI_SPAM_THRESHOLD = threshold
    await SettingsService(session).set_int("anti_spam_threshold", threshold)
    await callback.answer(f"✅ Threshold set to {threshold} clicks/s", show_alert=True)
    await callback.message.edit_reply_markup(reply_markup=anti_spam_keyboard(threshold))


@router.callback_query(F.data == "admin:set_support_username")
async def set_support_username_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminTextInputStates.entering_support_username)
    await callback.message.answer("Send the new support @username (without the @):")
    await callback.answer()


@router.message(AdminTextInputStates.entering_support_username)
async def set_support_username_apply(message: Message, session: AsyncSession, state: FSMContext) -> None:
    from bot.config import settings
    username = message.text.strip().lstrip("@")
    settings.SUPPORT_USERNAME = username
    await SettingsService(session).set("support_username", username)
    await state.clear()
    await message.answer(f"✅ Support username set to @{username}")
