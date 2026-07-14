from __future__ import annotations

import asyncio

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models.menu_button import MenuButtonAction
from bot.database.models.user import UserLanguage
from bot.filters.menu_action import MenuAction
from bot.fsm.user import PhotoEditorStates
from bot.keyboards.user.photo_editor import (
    collage_layout_keyboard,
    collage_progress_keyboard,
    frame_style_keyboard,
    rotation_keyboard,
    size_standard_keyboard,
    tool_selection_keyboard,
)
from bot.services.photo_service import PhotoService, RotationDirection
from bot.utils.i18n import t

router = Router(name="user:photo_editor")

# ponytail: fixed cap kept in-file rather than in Settings — this was already
# the documented limit before collage worked at all ("up to 6, one by one").
# If that needs to be admin-configurable later, move it into SettingsService;
# not worth the indirection for a single int nobody has asked to change.
MAX_COLLAGE_IMAGES = 6

_FRAME_COLORS = {
    "black": (0, 0, 0),
    "white": (255, 255, 255),
    "gold": (212, 175, 55),
}


async def _run_and_send(
    message: Message,
    fn,
    *args,
    filename: str,
    caption: str,
    locale: UserLanguage = UserLanguage.EN,
    **kwargs,
) -> None:
    """Runs a blocking PhotoService call off the event loop, with visible
    processing feedback. CPU-bound PIL work used to run inline on the loop —
    that's what was blocking the bot and causing bursty dispatch to trip
    AntiSpamMiddleware once the block cleared, not a rate-limiter bug."""
    processing = await message.answer(t("photo.processing", locale))
    try:
        result = await asyncio.to_thread(fn, *args, **kwargs)
    except Exception as exc:
        await processing.edit_text(t("photo.processing_error", locale, error=exc))
        return
    await processing.delete()
    await message.answer_document(BufferedInputFile(result, filename=filename), caption=caption)


async def _download(message_bot, file_id: str) -> bytes:
    file = await message_bot.get_file(file_id)
    bio = await message_bot.download_file(file.file_path)
    return bio.read()


def _parse_custom_size(raw: str) -> tuple[int, int] | None:
    """Parses 'WIDTHxHEIGHT' and enforces PIL resize bounds. Pulled out as a
    pure function so the parsing/validation is unit-testable without a
    Telegram Message object."""
    text = raw.lower().replace(" ", "")
    if "x" not in text:
        return None
    w_str, _, h_str = text.partition("x")
    if not (w_str.isdigit() and h_str.isdigit()):
        return None
    width, height = int(w_str), int(h_str)
    if not (1 <= width <= 6000 and 1 <= height <= 6000):
        return None
    return width, height


@router.message(MenuAction(MenuButtonAction.PHOTO_EDITOR))
async def open_photo_editor(message: Message, state: FSMContext, locale: UserLanguage = UserLanguage.EN) -> None:
    await state.clear()
    await state.set_state(PhotoEditorStates.selecting_tool)
    await message.answer(
        t("photo.editor_intro", locale),
        reply_markup=tool_selection_keyboard(locale),
    )


@router.callback_query(F.data.startswith("photo:"), PhotoEditorStates.selecting_tool)
async def handle_tool_selection(callback: CallbackQuery, state: FSMContext, locale: UserLanguage = UserLanguage.EN) -> None:
    tool = callback.data.split(":")[1]
    if tool == "cancel":
        await state.clear()
        await callback.message.edit_text(t("photo.editor_closed", locale))
        await callback.answer()
        return

    await state.update_data(tool=tool)

    if tool == "collage":
        await state.set_state(PhotoEditorStates.collecting_collage)
        await state.update_data(file_ids=[])
        await callback.message.edit_text(t("photo.collage_start", locale, max=MAX_COLLAGE_IMAGES))
        await callback.answer()
        return

    await state.set_state(PhotoEditorStates.awaiting_image)
    prompts = {
        "resize": t("photo.prompt_resize", locale),
        "rotate": t("photo.prompt_rotate", locale),
        "text": t("photo.prompt_text", locale),
        "frame": t("photo.prompt_frame", locale),
    }
    await callback.message.edit_text(prompts.get(tool, t("photo.prompt_generic", locale)))
    await callback.answer()


@router.message(F.photo, PhotoEditorStates.awaiting_image)
async def handle_photo_upload(message: Message, state: FSMContext, locale: UserLanguage = UserLanguage.EN) -> None:
    data = await state.get_data()
    tool = data.get("tool")
    img_bytes = await _download(message.bot, message.photo[-1].file_id)
    await state.update_data(img_bytes=img_bytes)

    if tool == "resize":
        await state.set_state(PhotoEditorStates.selecting_size)
        await message.answer(t("photo.pick_size", locale), reply_markup=size_standard_keyboard(locale))
    elif tool == "rotate":
        await state.set_state(PhotoEditorStates.selecting_rotation)
        await message.answer(t("photo.pick_direction", locale), reply_markup=rotation_keyboard(locale))
    elif tool == "frame":
        await state.set_state(PhotoEditorStates.selecting_frame)
        await message.answer(t("photo.pick_frame", locale), reply_markup=frame_style_keyboard(locale))
    elif tool == "text":
        await state.set_state(PhotoEditorStates.entering_text)
        await message.answer(t("photo.enter_overlay_text", locale))


@router.message(F.photo, PhotoEditorStates.collecting_collage)
async def handle_collage_photo(message: Message, state: FSMContext, locale: UserLanguage = UserLanguage.EN) -> None:
    data = await state.get_data()
    file_ids: list[str] = data.get("file_ids", [])

    if len(file_ids) >= MAX_COLLAGE_IMAGES:
        await message.answer(t("photo.collage_max_reached", locale, max=MAX_COLLAGE_IMAGES))
        return

    file_ids.append(message.photo[-1].file_id)
    await state.update_data(file_ids=file_ids)
    await message.answer(
        t("photo.collage_progress", locale, count=len(file_ids), max=MAX_COLLAGE_IMAGES),
        reply_markup=collage_progress_keyboard(len(file_ids), MAX_COLLAGE_IMAGES, locale),
    )


@router.callback_query(F.data == "photo:collage_finish", PhotoEditorStates.collecting_collage)
async def handle_collage_finish(callback: CallbackQuery, state: FSMContext, locale: UserLanguage = UserLanguage.EN) -> None:
    data = await state.get_data()
    if len(data.get("file_ids", [])) < 2:
        await callback.answer(t("photo.collage_need_more", locale), show_alert=True)
        return
    await state.set_state(PhotoEditorStates.selecting_collage_layout)
    await callback.message.edit_text(t("photo.collage_pick_layout", locale), reply_markup=collage_layout_keyboard(locale))
    await callback.answer()


@router.callback_query(F.data.startswith("photo:layout:"), PhotoEditorStates.selecting_collage_layout)
async def handle_collage_layout(callback: CallbackQuery, state: FSMContext, locale: UserLanguage = UserLanguage.EN) -> None:
    cols = int(callback.data.split(":")[2])
    data = await state.get_data()
    file_ids: list[str] = data.get("file_ids", [])
    await callback.answer()

    images = [await _download(callback.bot, fid) for fid in file_ids]
    photo_svc = PhotoService()
    await _run_and_send(
        callback.message,
        photo_svc.collage,
        images,
        filename="collage.jpg",
        caption=t("photo.collage_ready", locale, count=len(images), cols=cols),
        locale=locale,
        cols=cols,
    )
    await state.clear()


@router.callback_query(F.data.startswith("photo:size:"), PhotoEditorStates.selecting_size)
async def handle_size_selection(callback: CallbackQuery, state: FSMContext, locale: UserLanguage = UserLanguage.EN) -> None:
    parts = callback.data.split(":")
    await callback.answer()

    if parts[2] == "custom":
        await state.set_state(PhotoEditorStates.entering_custom_size)
        await callback.message.edit_text(t("photo.custom_size_prompt", locale))
        return

    width, height = int(parts[2]), int(parts[3])
    data = await state.get_data()
    photo_svc = PhotoService()
    await _run_and_send(
        callback.message,
        photo_svc.resize,
        data["img_bytes"], width, height,
        filename="resized.jpg",
        caption=t("photo.resized", locale, width=width, height=height),
        locale=locale,
    )
    await state.clear()


@router.message(PhotoEditorStates.entering_custom_size)
async def handle_custom_size(message: Message, state: FSMContext, locale: UserLanguage = UserLanguage.EN) -> None:
    # ponytail: bounds enforced in _parse_custom_size are a trust-boundary
    # check (user input feeds PIL's resize buffer allocation), not a product
    # decision — 6000px covers any legitimate use here.
    parsed = _parse_custom_size(message.text or "")
    if not parsed:
        await message.answer(t("photo.custom_size_invalid", locale))
        return
    width, height = parsed

    data = await state.get_data()
    photo_svc = PhotoService()
    await _run_and_send(
        message,
        photo_svc.resize,
        data["img_bytes"], width, height,
        filename="resized.jpg",
        caption=t("photo.resized", locale, width=width, height=height),
        locale=locale,
    )
    await state.clear()


@router.callback_query(F.data.startswith("photo:rot:"), PhotoEditorStates.selecting_rotation)
async def handle_rotation_selection(callback: CallbackQuery, state: FSMContext, locale: UserLanguage = UserLanguage.EN) -> None:
    direction = RotationDirection(callback.data.split(":")[2])
    data = await state.get_data()
    await callback.answer()

    photo_svc = PhotoService()
    await _run_and_send(
        callback.message,
        photo_svc.rotate,
        data["img_bytes"], direction,
        filename="rotated.jpg",
        caption=t("photo.done", locale),
        locale=locale,
    )
    await state.clear()


@router.callback_query(F.data.startswith("photo:frame:"), PhotoEditorStates.selecting_frame)
async def handle_frame_selection(callback: CallbackQuery, state: FSMContext, locale: UserLanguage = UserLanguage.EN) -> None:
    style = callback.data.split(":")[2]
    color = _FRAME_COLORS.get(style, (0, 0, 0))
    data = await state.get_data()
    await callback.answer()

    photo_svc = PhotoService()
    await _run_and_send(
        callback.message,
        photo_svc.add_frame,
        data["img_bytes"],
        filename="framed.jpg",
        caption=t("photo.done", locale),
        locale=locale,
        border_px=25,
        color=color,
    )
    await state.clear()


@router.message(PhotoEditorStates.entering_text)
async def handle_text_overlay(message: Message, state: FSMContext, locale: UserLanguage = UserLanguage.EN) -> None:
    data = await state.get_data()
    overlay_text = (message.text or "").strip()
    if not overlay_text:
        await message.answer(t("photo.overlay_text_empty", locale))
        return

    photo_svc = PhotoService()
    await _run_and_send(
        message,
        photo_svc.add_text,
        data["img_bytes"], overlay_text,
        filename="with_text.jpg",
        caption=t("photo.text_added", locale, text=overlay_text),
        locale=locale,
    )
    await state.clear()


@router.callback_query(
    F.data == "photo:back",
    StateFilter(
        PhotoEditorStates.selecting_size,
        PhotoEditorStates.selecting_rotation,
        PhotoEditorStates.selecting_frame,
        PhotoEditorStates.selecting_collage_layout,
    ),
)
async def handle_back_to_tools(callback: CallbackQuery, state: FSMContext, locale: UserLanguage = UserLanguage.EN) -> None:
    await state.set_state(PhotoEditorStates.selecting_tool)
    await callback.message.edit_text(
        t("photo.editor_intro", locale),
        reply_markup=tool_selection_keyboard(locale),
    )
    await callback.answer()


@router.callback_query(F.data == "photo:cancel", PhotoEditorStates.collecting_collage)
async def handle_collage_cancel(callback: CallbackQuery, state: FSMContext, locale: UserLanguage = UserLanguage.EN) -> None:
    await state.clear()
    await callback.message.edit_text(t("photo.editor_closed", locale))
    await callback.answer()
