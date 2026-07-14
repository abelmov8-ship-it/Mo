from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database.models.channel import ChannelCategory
from bot.database.models.menu_button import MenuButtonAction
from bot.database.models.user import UserLanguage
from bot.filters.menu_action import MenuAction
from bot.filters.text_key_match import TextKeyMatch
from bot.services.channel_service import ChannelService
from bot.utils.i18n import t
from bot.utils.one_time_links import generate_one_time_link

router = Router(name="user:channels")


def _categories_inline_keyboard(locale: UserLanguage) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("channels.free_label", locale), callback_data="channels:cat:free")
    builder.button(text=t("channels.vip_label", locale),  callback_data="channels:cat:vip")
    builder.adjust(1)
    return builder


def _categories_reply_keyboard(locale: UserLanguage) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text=t("channels.free_label", locale))
    builder.button(text=t("channels.vip_label", locale))
    builder.button(text=t("ui.back_to_menu", locale))
    builder.adjust(2, 1)
    return builder.as_markup(resize_keyboard=True)


@router.message(MenuAction(MenuButtonAction.CHANNELS))
async def show_categories(message: Message, locale: UserLanguage = UserLanguage.EN) -> None:
    if settings.CHANNELS_KEYBOARD_TYPE == "reply":
        await message.answer(t("channels.category_prompt", locale), reply_markup=_categories_reply_keyboard(locale))
    else:
        await message.answer(t("channels.category_prompt", locale),
                             reply_markup=_categories_inline_keyboard(locale).as_markup())


async def _channel_list_content(
    session: AsyncSession, category: ChannelCategory, locale: UserLanguage,
) -> tuple[str, InlineKeyboardBuilder] | None:
    """(text, inline_builder) for a category's channel list, or None if
    it's empty. Shared by the inline-tap and reply-keyboard-tap entry
    points below — the list itself is always inline either way (specific,
    dynamically-named items suit inline far better than a reply keyboard),
    only the category *picker* one level up switches between the two."""
    channels = await ChannelService(session).get_by_category(category)
    if not channels:
        return None

    builder = InlineKeyboardBuilder()
    for ch in channels:
        builder.button(text=ch.name, callback_data=f"channels:open:{ch.id}")
    builder.button(text=t("channels.back_button", locale), callback_data="channels:back")
    builder.adjust(1)

    label = t("channels.free_label", locale) if category == ChannelCategory.FREE else t("channels.vip_label", locale)
    return t("channels.select_channel", locale, label=label), builder


@router.callback_query(F.data.startswith("channels:cat:"))
async def show_channels(callback: CallbackQuery, session: AsyncSession, locale: UserLanguage = UserLanguage.EN) -> None:
    cat_str = callback.data.split(":")[2]
    category = ChannelCategory.FREE if cat_str == "free" else ChannelCategory.VIP

    if category == ChannelCategory.VIP:
        from bot.filters.is_vip import IsVip
        if not await IsVip()(callback, session):
            await callback.answer(t("channels.vip_only", locale), show_alert=True)
            return

    content = await _channel_list_content(session, category, locale)
    if content is None:
        await callback.answer(t("channels.empty_category", locale), show_alert=True)
        return

    text, builder = content
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


async def _show_channels_from_reply(
    message: Message, session: AsyncSession, locale: UserLanguage, category: ChannelCategory,
) -> None:
    """Reply-keyboard-tap equivalent of show_channels — same content, sent
    as a new message instead of an edit (a reply-keyboard tap arrives as a
    plain Message with nothing of the bot's own to edit). The [Free][VIP]
    [🏠 Main Menu] reply keyboard itself is untouched by this — it isn't
    tied to any one message, so it just stays visible underneath."""
    if category == ChannelCategory.VIP:
        from bot.filters.is_vip import IsVip
        if not await IsVip()(message, session):
            await message.answer(t("channels.vip_only", locale))
            return

    content = await _channel_list_content(session, category, locale)
    if content is None:
        await message.answer(t("channels.empty_category", locale))
        return

    text, builder = content
    await message.answer(text, reply_markup=builder.as_markup())


@router.message(TextKeyMatch("channels.free_label"))
async def show_free_channels_reply(message: Message, session: AsyncSession, locale: UserLanguage = UserLanguage.EN) -> None:
    await _show_channels_from_reply(message, session, locale, ChannelCategory.FREE)


@router.message(TextKeyMatch("channels.vip_label"))
async def show_vip_channels_reply(message: Message, session: AsyncSession, locale: UserLanguage = UserLanguage.EN) -> None:
    await _show_channels_from_reply(message, session, locale, ChannelCategory.VIP)


@router.callback_query(F.data.startswith("channels:open:"))
async def send_channel_link(callback: CallbackQuery, session: AsyncSession, locale: UserLanguage = UserLanguage.EN) -> None:
    channel_id = int(callback.data.split(":")[2])
    ch_svc = ChannelService(session)
    ch = await ch_svc.get_by_id(channel_id)

    if not ch:
        await callback.answer(t("channels.not_found", locale), show_alert=True)
        return

    link = await generate_one_time_link(callback.bot, ch)
    builder = InlineKeyboardBuilder()
    builder.button(text=t("channels.open_button", locale, name=ch.name), url=link)
    await callback.message.answer(
        t("channels.one_time_link", locale, name=ch.name),
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data == "channels:back")
async def back_to_categories(callback: CallbackQuery, locale: UserLanguage = UserLanguage.EN) -> None:
    text = t("channels.category_prompt_back", locale)
    if settings.CHANNELS_KEYBOARD_TYPE == "reply":
        # The reply keyboard is already showing and unaffected by this edit
        # either way — but the channel list's OWN inline [names...][Back]
        # buttons are still attached to this message and must be explicitly
        # cleared (an editMessageText call that omits reply_markup entirely
        # leaves the existing one in place per the Bot API, it doesn't
        # remove it), or they'd sit there doing nothing over "🎬 Choose a
        # category:" text that no longer matches them.
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[]))
    else:
        await callback.message.edit_text(text, reply_markup=_categories_inline_keyboard(locale).as_markup())
    await callback.answer()
