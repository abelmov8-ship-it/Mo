from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database.models.user import UserLanguage
from bot.utils.i18n import t


def tool_selection_keyboard(locale: UserLanguage = UserLanguage.EN) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("photo.tool_resize", locale),   callback_data="photo:resize")
    builder.button(text=t("photo.tool_rotate", locale),   callback_data="photo:rotate")
    builder.button(text=t("photo.tool_text", locale),     callback_data="photo:text")
    builder.button(text=t("photo.tool_frame", locale),    callback_data="photo:frame")
    builder.button(text=t("photo.tool_collage", locale),  callback_data="photo:collage")
    builder.button(text=t("photo.cancel_button", locale), callback_data="photo:cancel")
    builder.adjust(2)
    return builder.as_markup()


def size_standard_keyboard(locale: UserLanguage = UserLanguage.EN) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    # A-series (mm → 150 DPI px)
    builder.button(text=t("photo.size_a4", locale), callback_data="photo:size:1240:1754")
    builder.button(text=t("photo.size_a5", locale), callback_data="photo:size:874:1240")
    builder.button(text=t("photo.size_a6", locale), callback_data="photo:size:620:874")
    # B-series
    builder.button(text=t("photo.size_b4", locale), callback_data="photo:size:1476:2079")
    builder.button(text=t("photo.size_b5", locale), callback_data="photo:size:1039:1476")
    builder.button(text=t("photo.size_custom", locale), callback_data="photo:size:custom")
    builder.button(text=t("photo.back_button", locale),  callback_data="photo:back")
    builder.adjust(1)
    return builder.as_markup()


def rotation_keyboard(locale: UserLanguage = UserLanguage.EN) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("photo.rotate_ccw90", locale),     callback_data="photo:rot:ccw90")
    builder.button(text=t("photo.rotate_cw90", locale),      callback_data="photo:rot:cw90")
    builder.button(text=t("photo.flip_horizontal", locale),  callback_data="photo:rot:flip_h")
    builder.button(text=t("photo.flip_vertical", locale),    callback_data="photo:rot:flip_v")
    builder.button(text=t("photo.back_button", locale),      callback_data="photo:back")
    builder.adjust(2)
    return builder.as_markup()


def frame_style_keyboard(locale: UserLanguage = UserLanguage.EN) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("photo.frame_black", locale), callback_data="photo:frame:black")
    builder.button(text=t("photo.frame_white", locale), callback_data="photo:frame:white")
    builder.button(text=t("photo.frame_gold", locale),  callback_data="photo:frame:gold")
    builder.button(text=t("photo.back_button", locale), callback_data="photo:back")
    builder.adjust(2)
    return builder.as_markup()


def collage_progress_keyboard(count: int, max_count: int, locale: UserLanguage = UserLanguage.EN) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if count >= 2:
        builder.button(
            text=t("photo.collage_finish_button", locale, count=count, max=max_count),
            callback_data="photo:collage_finish",
        )
    builder.button(text=t("photo.cancel_button", locale), callback_data="photo:cancel")
    builder.adjust(1)
    return builder.as_markup()


def collage_layout_keyboard(locale: UserLanguage = UserLanguage.EN) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("photo.collage_2col", locale), callback_data="photo:layout:2")
    builder.button(text=t("photo.collage_3col", locale), callback_data="photo:layout:3")
    builder.button(text=t("photo.back_button", locale),  callback_data="photo:back")
    builder.adjust(2)
    return builder.as_markup()
