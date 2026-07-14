from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database.models.channel import Channel, ChannelCategory


def channels_list_keyboard(channels: list[Channel]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Add New Channel", callback_data="ch:add")
    for ch in channels:
        fj_icon = "🟢" if ch.force_join else "🔴"
        cat_label = "VIP" if ch.category == ChannelCategory.VIP else "Free"
        builder.button(
            text=f"{fj_icon} {ch.name} ({cat_label})",
            callback_data=f"ch:manage:{ch.id}",
        )
    builder.adjust(1)
    return builder.as_markup()


def channel_manage_keyboard(channel: Channel) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    fj_label = "🔴 Turn OFF Force Join" if channel.force_join else "🟢 Turn ON Force Join"
    builder.button(text=fj_label,               callback_data=f"ch:toggle_fj:{channel.id}")
    ts_label = "🔴 Remove as Trending Source" if channel.is_trending_source else "🔥 Set as Trending Source"
    builder.button(text=ts_label,               callback_data=f"ch:toggle_trending:{channel.id}")
    ai_label = "🔴 Remove as Auto-Index Source" if channel.is_auto_index_source else "📥 Set as Auto-Index Source"
    builder.button(text=ai_label,               callback_data=f"ch:toggle_autoindex:{channel.id}")
    builder.button(text="✏️ Edit Name",          callback_data=f"ch:edit_name:{channel.id}")
    builder.button(text="🔗 Edit URL",           callback_data=f"ch:edit_url:{channel.id}")
    builder.button(text="🆔 Set Channel ID",     callback_data=f"ch:edit_cid:{channel.id}")
    price_label = f"💰 Price: {channel.custom_ppv_price:.0f} Birr" if channel.custom_ppv_price is not None else "💰 Set Custom Price"
    builder.button(text=price_label,            callback_data=f"ch:edit_price:{channel.id}")
    builder.button(text="🗑️ Delete",            callback_data=f"ch:delete:{channel.id}")
    builder.button(text="⬅️ Back to List",       callback_data="ch:list")
    builder.adjust(1)
    return builder.as_markup()


def wizard_step1_keyboard() -> InlineKeyboardMarkup:
    """Step 1: category selection."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🆓 Free Channel", callback_data="ch:wiz:cat:free")
    builder.button(text="💎 VIP Channel",  callback_data="ch:wiz:cat:vip")
    builder.button(text="⬅️ Cancel",       callback_data="ch:wiz:cancel")
    builder.adjust(2, 1)
    return builder.as_markup()


def wizard_step2_keyboard() -> InlineKeyboardMarkup:
    """Step 2: Force Join toggle."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🟢 Active / Force Join ON",   callback_data="ch:wiz:fj:on")
    builder.button(text="🔴 Inactive / Force Join OFF", callback_data="ch:wiz:fj:off")
    builder.button(text="⬅️ Cancel",                    callback_data="ch:wiz:cancel")
    builder.adjust(1)
    return builder.as_markup()
