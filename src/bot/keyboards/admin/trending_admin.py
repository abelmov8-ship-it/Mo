from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database.models.trending_poster import TrendingPoster


def _poster_label(poster: TrendingPoster) -> str:
    if poster.caption:
        short = poster.caption.strip().splitlines()[0][:30]
        return short + ("…" if len(poster.caption.strip()) > 30 else "")
    return f"Poster #{poster.id} (no caption)"


def trending_list_keyboard(posters: list[TrendingPoster]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Add Poster", callback_data="trendadm:add")
    for poster in posters:
        vis_icon = "🟢" if poster.is_visible else "🔴"
        builder.button(text=f"{vis_icon} {_poster_label(poster)}", callback_data=f"trendadm:manage:{poster.id}")
    builder.adjust(1)
    return builder.as_markup()


def trending_manage_keyboard(poster: TrendingPoster, *, is_first: bool, is_last: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    vis_label = "🔴 Hide" if poster.is_visible else "🟢 Show"
    builder.button(text=vis_label, callback_data=f"trendadm:toggle_vis:{poster.id}")
    if not is_first:
        builder.button(text="⬆️ Move Up", callback_data=f"trendadm:move:{poster.id}:up")
    if not is_last:
        builder.button(text="⬇️ Move Down", callback_data=f"trendadm:move:{poster.id}:down")
    builder.button(text="🗑️ Delete", callback_data=f"trendadm:delete:{poster.id}")
    builder.button(text="⬅️ Back to List", callback_data="trendadm:list")
    builder.adjust(1)
    return builder.as_markup()
