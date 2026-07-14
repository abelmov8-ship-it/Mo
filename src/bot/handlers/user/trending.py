from aiogram import Router
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models.menu_button import MenuButtonAction
from bot.database.models.user import UserLanguage
from bot.filters.menu_action import MenuAction
from bot.services.trending_poster_service import TrendingPosterService
from bot.utils.i18n import t

router = Router(name="user:trending")


@router.message(MenuAction(MenuButtonAction.TRENDING))
async def show_trending(message: Message, session: AsyncSession, locale: UserLanguage = UserLanguage.EN) -> None:
    """Posters/images only, curated by an admin from designated channels —
    see handlers/admin/trending_admin.py. This never touches the movies
    table and never delivers a real file, regardless of VIP or PPV status;
    that's the whole point of this section existing separately from
    Search. Do not add a movie/PPV lookup back into this function."""
    posters = await TrendingPosterService(session).get_visible()

    if not posters:
        await message.answer(t("trending.empty", locale))
        return

    for poster in posters:
        await message.answer_photo(photo=poster.image_file_id, caption=poster.caption or None)
