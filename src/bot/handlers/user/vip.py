from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models.menu_button import MenuButtonAction
from bot.database.models.user import UserLanguage
from bot.filters.menu_action import MenuAction
from bot.services.subscription_service import SubscriptionService
from bot.keyboards.user.payment import vip_plans_keyboard
from bot.utils.i18n import t

router = Router(name="user:vip")


@router.message(MenuAction(MenuButtonAction.VIP_PACKAGE))
async def show_vip_packages(message: Message, session: AsyncSession, locale: UserLanguage = UserLanguage.EN) -> None:
    sub_svc = SubscriptionService(session)
    prices = await sub_svc.get_all_prices()

    await message.answer(
        t("vip.packages_intro", locale),
        reply_markup=vip_plans_keyboard(prices, locale),
    )


@router.callback_query(F.data == "nav:vip")
async def show_vip_packages_inline(callback: CallbackQuery, session: AsyncSession, locale: UserLanguage = UserLanguage.EN) -> None:
    """Same as show_vip_packages, reached from an inline button (e.g. the
    PPV "Upgrade to VIP" fallback) instead of the reply-keyboard menu."""
    sub_svc = SubscriptionService(session)
    prices = await sub_svc.get_all_prices()
    await callback.answer()
    await callback.message.edit_text(
        t("vip.packages_intro_short", locale),
        reply_markup=vip_plans_keyboard(prices, locale),
    )


@router.callback_query(F.data.startswith("buy_vip:"))
async def handle_vip_plan_selection(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext,
    locale: UserLanguage = UserLanguage.EN,
) -> None:
    from bot.database.models.subscription import PlanDuration
    plan_val = callback.data.split(":")[1]
    try:
        plan = PlanDuration(plan_val)
    except ValueError:
        await callback.answer(t("vip.invalid_plan", locale), show_alert=True)
        return

    sub_svc = SubscriptionService(session)
    price = await sub_svc.get_price(plan)

    # ponytail: was previously never written — payment.py reads this same
    # key, so every purchase silently fell back to the 1-Month price
    # regardless of what the user picked. Fixed at the source (here) rather
    # than guessed-around in the payment handler.
    #
    # Also clears any stale topup_amount: _payment_intent() in payment.py
    # checks for a top-up amount first, so an earlier abandoned wallet
    # top-up left sitting in state data would otherwise outrank this fresh
    # plan selection and charge for the wrong thing.
    data = await state.get_data()
    data.pop("topup_amount", None)
    data["selected_plan"] = plan_val
    await state.set_data(data)

    price_str = f"{price:.0f}"
    await callback.answer(t("vip.plan_selected_toast", locale, plan=plan_val, price=price_str))
    await callback.message.edit_text(
        t("vip.plan_selected", locale, plan=plan_val, price=price_str)
    )
