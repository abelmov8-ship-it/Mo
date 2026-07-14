from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database.models.user import UserLanguage
from bot.filters.is_admin import IsAdmin
from bot.handlers.user.start import render_main_menu
from bot.keyboards.admin.panel import admin_panel_keyboard
from bot.utils.i18n import t

router = Router(name="admin:panel")
router.message.filter(IsAdmin())


@router.message(F.text == "🛠 Admin Panel")
async def open_admin_panel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "🛠 <b>Admin Panel</b>\n\nSelect a section:",
        reply_markup=admin_panel_keyboard(),
    )


@router.message(F.text == "⬅️ Back to Main Menu")
async def back_to_main(
    message: Message, session: AsyncSession, state: FSMContext,
    locale: UserLanguage = UserLanguage.EN,
) -> None:
    await state.clear()
    await render_main_menu(message, session, is_admin=True, text=t("start.back_to_main", locale), locale=locale)


@router.message(F.text == "⬅️ Back to Admin")
async def back_to_admin_panel(message: Message, state: FSMContext) -> None:
    """Used by every admin sub-menu (System Tools, Analytics, ...) to return
    one level up — was rendered in those keyboards with no handler at all."""
    await state.clear()
    await message.answer(
        "🛠 <b>Admin Panel</b>\n\nSelect a section:",
        reply_markup=admin_panel_keyboard(),
    )
