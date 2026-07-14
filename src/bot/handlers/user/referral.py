from aiogram import Router
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database.models.menu_button import MenuButtonAction
from bot.filters.menu_action import MenuAction
from bot.services.referral_service import ReferralService
from bot.services.user_service import UserService
from bot.utils.i18n import t

router = Router(name="user:referral")


@router.message(MenuAction(MenuButtonAction.REFERRAL))
async def show_referral(message: Message, session: AsyncSession) -> None:
    user_svc = UserService(session)
    user = await user_svc.get_by_telegram_id(message.from_user.id)
    if not user:
        await message.answer(t("referral.start_first"))
        return

    ref_svc = ReferralService(session)
    ref = await ref_svc.get_or_create(user)

    bot_info = await message.bot.get_me()
    link = ref_svc.build_deep_link(bot_info.username, ref.referral_code)

    milestone = settings.REFERRAL_MILESTONE
    reward_days = settings.REFERRAL_REWARD_DAYS
    remaining = milestone - (ref.invite_count % milestone)

    await message.answer(
        t(
            "referral.summary", user.language,
            reward_days=reward_days, milestone=milestone, link=link,
            invite_count=ref.invite_count, remaining=remaining,
        )
    )
