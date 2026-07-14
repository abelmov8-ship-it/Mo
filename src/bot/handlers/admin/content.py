from __future__ import annotations

from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.filters.is_admin import IsAdmin
from bot.fsm.admin import ContentDeployStates
from bot.handlers.admin.welcome_buttons import validate_button_url
from bot.services.channel_service import ChannelService
from bot.tasks.content_scheduler import queue_post

router = Router(name="admin:content")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

# ponytail: same cap philosophy as the photo editor's collage limit — a post
# with more social links than this looks broken regardless of how the admin
# got there, so it's a fixed sanity ceiling, not a product decision.
MAX_SOCIAL_BUTTONS = 6

# Telegram's own hard limit on photo/video captions.
_CAPTION_MAX_LEN = 1024


@router.message(F.text == "📤 Post to Channel")
async def content_deploy_start(message: Message, session: AsyncSession, state: FSMContext) -> None:
    ch_svc = ChannelService(session)
    channels = await ch_svc.get_all()

    if not channels:
        await message.answer("No channels configured yet. Add a channel first.")
        return

    builder = InlineKeyboardBuilder()
    for ch in channels:
        builder.button(text=ch.name, callback_data=f"deploy:ch:{ch.id}")
    builder.button(text="❌ Cancel", callback_data="deploy:cancel")
    builder.adjust(1)

    await state.set_state(ContentDeployStates.selecting_channel)
    await message.answer("📤 <b>Post to Channel</b>\n\nSelect target channel:",
                         reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("deploy:ch:"), ContentDeployStates.selecting_channel)
async def deploy_channel_selected(callback: CallbackQuery, state: FSMContext) -> None:
    ch_id = int(callback.data.split(":")[2])
    await state.update_data(target_channel_id=ch_id)
    await state.set_state(ContentDeployStates.uploading_media)
    await callback.message.edit_text(
        "Step 2 — Upload a photo or video (or send text only for a text post):"
    )
    await callback.answer()


def _skip_caption_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➡️ Skip Caption", callback_data="deploy:skip_caption")
    return builder.as_markup()


@router.message(F.photo | F.video | F.text, ContentDeployStates.uploading_media)
async def deploy_media_received(message: Message, state: FSMContext) -> None:
    photo_id = message.photo[-1].file_id if message.photo else None
    video_id = message.video.file_id if message.video else None

    if photo_id or video_id:
        # Media posts get a dedicated caption step next, rather than reusing
        # whatever Telegram's own attached-caption field happened to hold —
        # that's easy to miss and gives no explicit Skip.
        await state.update_data(photo_id=photo_id, video_id=video_id)
        await state.set_state(ContentDeployStates.entering_caption)
        await message.answer("Step 3 — Send a caption for this post, or skip:",
                             reply_markup=_skip_caption_keyboard())
        return

    # Text-only post: the text itself is the content. Telegram text messages
    # don't have a separate caption concept, so there's nothing to ask for
    # here that the admin hasn't already typed.
    await state.update_data(photo_id=None, video_id=None, caption=message.text or "", post_buttons=[])
    await state.set_state(ContentDeployStates.adding_buttons)
    await message.answer(_buttons_status_text([]), reply_markup=_buttons_menu_keyboard([]))


@router.message(F.text, ContentDeployStates.entering_caption)
async def deploy_caption_received(message: Message, state: FSMContext) -> None:
    caption = (message.text or "").strip()
    if len(caption) > _CAPTION_MAX_LEN:
        await message.answer(f"❌ Captions must be under {_CAPTION_MAX_LEN} characters (Telegram's limit). Try again:")
        return
    await state.update_data(caption=caption, post_buttons=[])
    await state.set_state(ContentDeployStates.adding_buttons)
    await message.answer(_buttons_status_text([]), reply_markup=_buttons_menu_keyboard([]))


@router.callback_query(F.data == "deploy:skip_caption", ContentDeployStates.entering_caption)
async def deploy_caption_skip(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(caption="", post_buttons=[])
    await state.set_state(ContentDeployStates.adding_buttons)
    await callback.message.edit_text(_buttons_status_text([]), reply_markup=_buttons_menu_keyboard([]))
    await callback.answer()


# ── Buttons: Watch / Reactions toggle on/off; social links accumulate ──────

def _buttons_menu_keyboard(post_buttons: list[dict]) -> InlineKeyboardMarkup:
    has_watch = any(b["kind"] == "watch" for b in post_buttons)
    has_reactions = any(b["kind"] == "reactions" for b in post_buttons)
    social_count = sum(1 for b in post_buttons if b["kind"] == "url")

    builder = InlineKeyboardBuilder()
    builder.button(text=("✅ " if has_watch else "") + "🎬 Watch Button", callback_data="deploy:btn:watch")
    builder.button(text=("✅ " if has_reactions else "") + "👍 Reaction Buttons", callback_data="deploy:btn:reactions")
    if social_count < MAX_SOCIAL_BUTTONS:
        builder.button(text="🔗 Add Social Media Button", callback_data="deploy:btn:add_social")
    builder.button(text="➡️ Done", callback_data="deploy:btn:done")
    builder.adjust(1)
    return builder.as_markup()


def _buttons_status_text(post_buttons: list[dict]) -> str:
    if not post_buttons:
        return "Step 4 — Add buttons to this post? All optional — tap Done to skip."
    parts = []
    for b in post_buttons:
        if b["kind"] == "watch":
            parts.append("🎬 Watch")
        elif b["kind"] == "reactions":
            parts.append("👍/👎 Reactions")
        else:
            parts.append(f"🔗 {b['label']}")
    return "Step 4 — Current buttons: " + ", ".join(parts) + "\nAdd more, or tap Done."


def _toggle_fixed_button(post_buttons: list[dict], kind: str) -> list[dict]:
    """watch/reactions are on/off toggles — tapping again removes them,
    unlike social links which can have several at once. Pulled out as a
    pure function so the toggle logic is unit-testable without a
    CallbackQuery."""
    if any(b["kind"] == kind for b in post_buttons):
        return [b for b in post_buttons if b["kind"] != kind]
    return post_buttons + [{"kind": kind}]


@router.callback_query(F.data.startswith("deploy:btn:"), ContentDeployStates.adding_buttons)
async def deploy_buttons_menu(callback: CallbackQuery, state: FSMContext) -> None:
    kind = callback.data.split(":")[2]
    data = await state.get_data()
    post_buttons: list[dict] = data.get("post_buttons", [])

    if kind == "done":
        await state.set_state(ContentDeployStates.confirming)
        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Post Now",       callback_data="deploy:confirm")
        builder.button(text="📅 Schedule Later", callback_data="deploy:schedule")
        builder.button(text="❌ Cancel",         callback_data="deploy:cancel")
        builder.adjust(1)
        await callback.message.edit_text("Step 5 — Ready to post. Post now, or schedule for later?",
                                         reply_markup=builder.as_markup())
        await callback.answer()
        return

    if kind == "add_social":
        await state.set_state(ContentDeployStates.entering_social_label)
        await callback.message.edit_text("Send the button's label (e.g. 📱 Follow on TikTok):")
        await callback.answer()
        return

    post_buttons = _toggle_fixed_button(post_buttons, kind)
    await state.update_data(post_buttons=post_buttons)
    await callback.message.edit_text(_buttons_status_text(post_buttons),
                                     reply_markup=_buttons_menu_keyboard(post_buttons))
    await callback.answer()


@router.message(ContentDeployStates.entering_social_label)
async def deploy_social_label(message: Message, state: FSMContext) -> None:
    label = (message.text or "").strip()
    if not label:
        await message.answer("❌ Send some text for the button label.")
        return
    if len(label) > 64:
        await message.answer("❌ Keep it under 64 characters.")
        return
    await state.update_data(pending_social_label=label)
    await state.set_state(ContentDeployStates.entering_social_url)
    await message.answer("Now send the URL this button should open (must start with https://):")


@router.message(ContentDeployStates.entering_social_url)
async def deploy_social_url(message: Message, state: FSMContext) -> None:
    url = validate_button_url(message.text or "")
    if not url:
        await message.answer("❌ The URL must start with https:// (or http:// / tg://) and be under 512 characters. Try again:")
        return

    data = await state.get_data()
    post_buttons: list[dict] = data.get("post_buttons", [])
    post_buttons.append({"kind": "url", "label": data["pending_social_label"], "url": url})
    await state.update_data(post_buttons=post_buttons, pending_social_label=None)
    await state.set_state(ContentDeployStates.adding_buttons)
    await message.answer(
        f"✅ Added.\n\n{_buttons_status_text(post_buttons)}",
        reply_markup=_buttons_menu_keyboard(post_buttons),
    )


def _build_post_markup(data: dict, bot_username: str) -> InlineKeyboardMarkup | None:
    post_buttons: list[dict] = data.get("post_buttons", [])
    if not post_buttons:
        return None

    builder = InlineKeyboardBuilder()
    for btn in post_buttons:
        if btn["kind"] == "watch":
            builder.button(text="🎬 Watch in Bot", url=f"https://t.me/{bot_username}")
        elif btn["kind"] == "reactions":
            builder.button(text="👍", callback_data="react:like")
            builder.button(text="👎", callback_data="react:dislike")
        elif btn["kind"] == "url":
            builder.button(text=btn["label"], url=btn["url"])
    builder.adjust(2)
    return builder.as_markup()


@router.callback_query(F.data == "deploy:confirm", ContentDeployStates.confirming)
async def deploy_confirm(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    ch_svc = ChannelService(session)
    ch = await ch_svc.get_by_id(data["target_channel_id"])

    if not ch or not ch.channel_id:
        await callback.answer("Channel ID not configured. Add the numeric channel_id first.", show_alert=True)
        await state.clear()
        return

    bot_info = await callback.bot.get_me()
    markup = _build_post_markup(data, bot_info.username)
    caption = data.get("caption", "")

    try:
        if data.get("photo_id"):
            await callback.bot.send_photo(ch.channel_id, photo=data["photo_id"],
                                          caption=caption, reply_markup=markup)
        elif data.get("video_id"):
            await callback.bot.send_video(ch.channel_id, video=data["video_id"],
                                          caption=caption, reply_markup=markup)
        else:
            await callback.bot.send_message(ch.channel_id, caption, reply_markup=markup)

        await callback.message.edit_text(f"✅ Posted to <b>{ch.name}</b> successfully!")
    except Exception as exc:
        await callback.message.edit_text(f"❌ Failed to post: {exc}")

    await state.clear()
    await callback.answer()


@router.callback_query(F.data == "deploy:schedule", ContentDeployStates.confirming)
async def deploy_schedule_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ContentDeployStates.entering_schedule_time)
    await callback.message.edit_text(
        "📅 When should this post go out? Send a date and time in UTC, "
        "as <code>YYYY-MM-DD HH:MM</code> (e.g. <code>2026-07-05 20:30</code>)."
    )
    await callback.answer()


@router.message(ContentDeployStates.entering_schedule_time)
async def deploy_schedule_apply(message: Message, session: AsyncSession, state: FSMContext) -> None:
    try:
        fire_at = datetime.strptime(message.text.strip(), "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    except ValueError:
        await message.answer("❌ Use the format YYYY-MM-DD HH:MM, e.g. 2026-07-05 20:30 (UTC).")
        return

    if fire_at <= datetime.now(timezone.utc):
        await message.answer("❌ That time is in the past. Send a future date/time.")
        return

    data = await state.get_data()
    ch = await ChannelService(session).get_by_id(data["target_channel_id"])
    if not ch or not ch.channel_id:
        await message.answer("❌ Channel ID not configured. Add the numeric channel_id first.")
        await state.clear()
        return

    bot_info = await message.bot.get_me()
    markup = _build_post_markup(data, bot_info.username)

    queue_post(
        channel_id=ch.channel_id,
        text=data.get("caption", ""),
        fire_at=fire_at,
        photo_id=data.get("photo_id"),
        video_id=data.get("video_id"),
        markup=markup,
    )
    await state.clear()
    await message.answer(
        f"✅ Post scheduled for <b>{ch.name}</b> at <code>{fire_at:%Y-%m-%d %H:%M}</code> UTC."
    )


@router.callback_query(F.data == "deploy:cancel")
async def deploy_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("❌ Post cancelled.")
    await callback.answer()
