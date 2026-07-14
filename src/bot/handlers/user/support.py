from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database.models.menu_button import MenuButtonAction
from bot.database.models.user import UserLanguage
from bot.filters.menu_action import MenuAction
from bot.fsm.user import SupportStates
from bot.services.settings_service import SettingsService
from bot.utils.i18n import t

router = Router(name="user:support")


@router.message(MenuAction(MenuButtonAction.SUPPORT))
async def open_support(message: Message, state: FSMContext, locale: UserLanguage = UserLanguage.EN) -> None:
    await state.clear()
    builder = InlineKeyboardBuilder()
    builder.button(text=t("support.contact_button", locale), callback_data="support:contact")
    builder.button(text=t("support.faq_button", locale),     callback_data="support:faq")
    builder.adjust(1)
    await message.answer(
        t("support.center_intro", locale),
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data == "support:faq")
async def show_faq(callback, session: AsyncSession, locale: UserLanguage = UserLanguage.EN) -> None:
    faq = await SettingsService(session).get_faq()
    visible = sorted((f for f in faq if f.get("is_visible", True)), key=lambda f: f.get("order", 0))

    if not visible:
        await callback.message.edit_text(t("support.faq_empty", locale))
        await callback.answer()
        return

    lines = [t("support.faq_header", locale)]
    for i, f in enumerate(visible, 1):
        lines.append(f"<b>{i}. {f['question']}</b>\n{f['answer']}\n")
    await callback.message.edit_text("\n".join(lines))
    await callback.answer()


@router.callback_query(F.data == "support:contact")
async def contact_support(callback, state: FSMContext, locale: UserLanguage = UserLanguage.EN) -> None:
    await state.set_state(SupportStates.composing_message)
    await callback.message.edit_text(t("support.contact_prompt", locale))
    await callback.answer()


@router.message(SupportStates.composing_message)
async def forward_ticket(message: Message, state: FSMContext, locale: UserLanguage = UserLanguage.EN) -> None:
    user = message.from_user
    ticket_text = (
        f"📨 <b>Support Ticket</b>\n\n"
        f"From: {user.first_name} (<code>{user.id}</code>)\n\n"
        f"<blockquote>{message.text}</blockquote>"
    )
    sent = 0
    for admin_id in settings.ADMIN_IDS:
        try:
            await message.bot.send_message(admin_id, ticket_text)
            sent += 1
        except Exception:
            pass

    if sent:
        await message.answer(t("support.ticket_sent", locale))
    else:
        support_handle = f"@{settings.SUPPORT_USERNAME}" if settings.SUPPORT_USERNAME else "the admin"
        await message.answer(t("support.ticket_failed", locale, handle=support_handle))

    await state.clear()
