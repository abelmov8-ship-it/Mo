from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message, PhotoSize
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database.models.menu_button import MenuButtonAction
from bot.database.models.payment import PaymentGateway, PaymentType
from bot.database.models.subscription import PlanDuration
from bot.database.models.user import UserLanguage
from bot.filters.menu_action import MenuAction
from bot.filters.text_key_match import TextKeyMatch
from bot.fsm.user import PaymentStates
from bot.keyboards.admin.payment import receipt_action_keyboard
from bot.keyboards.user.payment import payment_methods_keyboard, payment_methods_reply_keyboard, receipt_cancel_keyboard
from bot.services.chapa_service import ChapaError, ChapaService
from bot.services.chapa_fulfillment import FulfillOutcome, finalize_chapa_payment
from bot.services.payment_service import PaymentService
from bot.services.settings_service import SettingsService
from bot.services.subscription_service import SubscriptionService
from bot.services.user_service import UserService
from bot.services.wallet_service import WalletService
from bot.utils.formatters import format_payment_pending, format_vip_granted
from bot.utils.i18n import t

router = Router(name="user:payment")
logger = logging.getLogger(__name__)


async def _send_payment_methods(
    message: Message, session: AsyncSession, locale: UserLanguage, intro_text: str, wallet_balance: float,
) -> None:
    """The payment-method picker (Chapa/Bank/Wallet), reply or inline per
    settings.PAYMENT_KEYBOARD_TYPE. Shared by open_payment_menu (fresh
    entry from the main menu) and handle_topup_amount (reached after
    typing a wallet top-up amount) — both show this exact screen, so the
    reply/inline branch is written once rather than twice."""
    banks = await SettingsService(session).get_banks()
    if settings.PAYMENT_KEYBOARD_TYPE == "reply":
        await message.answer(
            intro_text,
            reply_markup=payment_methods_reply_keyboard(
                chapa_enabled=settings.CHAPA_ENABLED, has_banks=bool(banks),
                wallet_balance=wallet_balance, locale=locale,
            ),
        )
    else:
        await message.answer(
            intro_text,
            reply_markup=payment_methods_keyboard(
                chapa_enabled=settings.CHAPA_ENABLED, has_banks=bool(banks),
                wallet_balance=wallet_balance, locale=locale,
            ),
        )


@router.message(MenuAction(MenuButtonAction.PAYMENT))
async def open_payment_menu(message: Message, session: AsyncSession, state: FSMContext) -> None:
    user_svc = UserService(session)
    user = await user_svc.get_by_telegram_id(message.from_user.id)
    wallet_bal = user.wallet_balance if user else 0.0
    locale = user.language if user else UserLanguage.EN

    await _send_payment_methods(message, session, locale, t("payment.menu_intro", locale), wallet_bal)
    # Note: doesn't clear state data here — if the user arrived via "Tap
    # 💳 Payment to complete your purchase" after picking a VIP plan, that
    # selection lives in state data and needs to survive this screen.
    await state.set_state(PaymentStates.selecting_method)


async def _selected_plan(state: FSMContext) -> PlanDuration:
    # ponytail: silently defaults to 1-Month if the user reaches the
    # payment method screen without ever picking a plan (e.g. tapping
    # 💳 Payment directly from the main menu). Ceiling: they get charged
    # for a plan they didn't explicitly choose. Upgrade path is a "no plan
    # selected — pick one" interstitial here instead of a default.
    data = await state.get_data()
    plan_val = data.get("selected_plan", PlanDuration.ONE_MONTH.value)
    try:
        return PlanDuration(plan_val)
    except ValueError:
        return PlanDuration.ONE_MONTH


async def _payment_intent(session: AsyncSession, state: FSMContext) -> tuple[float, PaymentType, str | None]:
    """Resolves what this payment is actually for: a wallet top-up (fixed
    amount the user typed) or a VIP plan purchase (price looked up from the
    selected plan). Every payment-method handler below shares this instead
    of each re-deriving amount/type/plan its own way."""
    data = await state.get_data()
    if data.get("topup_amount"):
        return data["topup_amount"], PaymentType.WALLET_TOPUP, None
    plan = await _selected_plan(state)
    sub_svc = SubscriptionService(session)
    amount = await sub_svc.get_price(plan)
    return amount, PaymentType.VIP, plan.value


async def _bank_transfer_text(session: AsyncSession, locale: UserLanguage, amount: float) -> str:
    """The bank-transfer screen's text — shared by the inline-callback and
    reply-keyboard entry points below, which only differ in how they send
    it (edit vs new message)."""
    banks = await SettingsService(session).get_banks()
    bank_lines = "\n\n".join(
        t("payment.bank_line", locale, name=b["name"], account=b["account"], holder=b["holder"])
        for b in banks
    ) or t("payment.no_banks", locale)
    return t("payment.bank_transfer_intro", locale, amount=f"{amount:.0f}", bank_lines=bank_lines)


@router.callback_query(F.data == "pay:bank", PaymentStates.selecting_method)
async def handle_bank_payment(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession,
    locale: UserLanguage = UserLanguage.EN,
) -> None:
    amount, payment_type, plan = await _payment_intent(session, state)
    text = await _bank_transfer_text(session, locale, amount)
    await state.set_state(PaymentStates.awaiting_receipt)
    await state.update_data(amount=amount, gateway=PaymentGateway.BANK.value, payment_type=payment_type.value, plan=plan)
    await callback.message.edit_text(text, reply_markup=receipt_cancel_keyboard(locale))
    await callback.answer()


@router.message(TextKeyMatch("payment.bank_button"), PaymentStates.selecting_method)
async def handle_bank_payment_reply(message: Message, state: FSMContext, session: AsyncSession, locale: UserLanguage = UserLanguage.EN) -> None:
    amount, payment_type, plan = await _payment_intent(session, state)
    text = await _bank_transfer_text(session, locale, amount)
    await state.set_state(PaymentStates.awaiting_receipt)
    await state.update_data(amount=amount, gateway=PaymentGateway.BANK.value, payment_type=payment_type.value, plan=plan)
    await message.answer(text, reply_markup=receipt_cancel_keyboard(locale))


@router.message(F.photo, PaymentStates.awaiting_receipt)
async def handle_receipt_upload(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    photo: PhotoSize = message.photo[-1]
    data = await state.get_data()

    user_svc = UserService(session)
    user = await user_svc.get_by_telegram_id(message.from_user.id)
    if not user:
        await state.clear()
        return

    payment_svc = PaymentService(session)
    payment = await payment_svc.create(
        user_id=user.id,
        amount=data.get("amount", 0.0),
        gateway=PaymentGateway(data.get("gateway", PaymentGateway.BANK.value)),
        payment_type=PaymentType(data.get("payment_type", PaymentType.VIP.value)),
        plan=data.get("plan"),
    )
    await payment_svc.attach_receipt(payment.id, photo.file_id)

    # Notify admins — deliberately fixed English; see the "Zero Hardcoding"
    # summary for why admin-only screens are out of scope for this system.
    for admin_id in settings.ADMIN_IDS:
        try:
            await message.bot.send_photo(
                chat_id=admin_id,
                photo=photo.file_id,
                caption=(
                    f"💳 <b>New Payment Receipt</b>\n\n"
                    f"User: {user.first_name} (<code>{user.telegram_id}</code>)\n"
                    f"Amount: <b>{payment.amount:.0f} Birr</b>\n"
                    f"Type: {payment.payment_type.value}\n"
                    f"Gateway: {payment.gateway.value}\n"
                    f"Plan: {payment.plan or 'N/A'}"
                ),
                reply_markup=receipt_action_keyboard(payment.id),
            )
        except Exception:
            pass

    await message.answer(format_payment_pending(payment.amount, payment.gateway.value, locale=user.language))
    await state.set_state(PaymentStates.pending_approval)


@router.callback_query(F.data == "pay:cancel")
async def cancel_payment(callback: CallbackQuery, state: FSMContext, locale: UserLanguage = UserLanguage.EN) -> None:
    await state.clear()
    await callback.message.edit_text(t("payment.cancelled", locale))
    await callback.answer()


# ── Chapa checkout ───────────────────────────────────────────────────────────

async def _initiate_chapa_checkout(
    session: AsyncSession, state: FSMContext, user, locale: UserLanguage,
) -> tuple[str, InlineKeyboardBuilder] | str:
    """(text, builder) for the checkout screen, or a plain error string.
    Shared by the inline-callback and reply-keyboard entry points below —
    the actual Chapa API call and persisting the payment row happen
    exactly once, here, regardless of which triggered it."""
    amount, payment_type, plan = await _payment_intent(session, state)
    try:
        chapa = ChapaService()
        # ponytail: Telegram never gives us an email, and Chapa requires
        # one. A synthetic per-user placeholder is enough for Chapa's
        # checkout form to accept the request — it's never actually
        # emailed to anyone. Ceiling: if Chapa starts validating email
        # deliverability this will need a real "ask the user for their
        # email" step instead.
        result = await chapa.initiate_payment(
            amount=amount,
            email=f"user{user.telegram_id}@telegram.local",
            first_name=user.first_name or "User",
            return_url="https://t.me",
            callback_url=f"{settings.PUBLIC_BASE_URL}/webhooks/chapa" if settings.PUBLIC_BASE_URL else "",
        )
    except ChapaError as exc:
        logger.warning("Chapa initiate failed: %s", exc)
        return t("payment.chapa_init_failed", locale)

    checkout_url = result.get("data", {}).get("checkout_url")
    tx_ref = result["tx_ref"]
    if not checkout_url:
        return t("payment.chapa_no_checkout_url", locale)

    # Persist the pending payment now, not after verification — this row is
    # what the webhook (bot.webapp.chapa_webhook_handler) looks up by
    # tx_ref, and a server-to-server webhook has no FSMContext/callback_data
    # to read "what this payment is for" from, only whatever's in the DB.
    await PaymentService(session).create(
        user_id=user.id, amount=amount, gateway=PaymentGateway.CHAPA,
        payment_type=payment_type, plan=plan, reference=tx_ref,
    )

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=t("payment.pay_now_button", locale), url=checkout_url))
    builder.button(text=t("payment.verify_button", locale), callback_data=f"pay:chapa_verify:{tx_ref}")
    builder.button(text=t("payment.cancel_button", locale), callback_data="pay:cancel")
    builder.adjust(1)
    return t("payment.chapa_checkout_intro", locale, amount=f"{amount:.0f}"), builder


@router.callback_query(F.data == "pay:chapa", PaymentStates.selecting_method)
async def handle_chapa_payment(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession,
    locale: UserLanguage = UserLanguage.EN,
) -> None:
    if not settings.CHAPA_ENABLED:
        await callback.answer(t("payment.chapa_unavailable", locale), show_alert=True)
        return

    user = await UserService(session).get_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer(t("payment.start_first", locale), show_alert=True)
        return
    locale = user.language

    await callback.answer()
    result = await _initiate_chapa_checkout(session, state, user, locale)
    if isinstance(result, str):
        await callback.message.answer(result)
        return
    text, builder = result
    await callback.message.edit_text(text, reply_markup=builder.as_markup())


@router.message(TextKeyMatch("payment.chapa_button"), PaymentStates.selecting_method)
async def handle_chapa_payment_reply(
    message: Message, state: FSMContext, session: AsyncSession, locale: UserLanguage = UserLanguage.EN,
) -> None:
    if not settings.CHAPA_ENABLED:
        await message.answer(t("payment.chapa_unavailable", locale))
        return

    user = await UserService(session).get_by_telegram_id(message.from_user.id)
    if not user:
        await message.answer(t("payment.start_first", locale))
        return
    locale = user.language

    result = await _initiate_chapa_checkout(session, state, user, locale)
    if isinstance(result, str):
        await message.answer(result)
        return
    text, builder = result
    await message.answer(text, reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("pay:chapa_verify:"))
async def verify_chapa_payment(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext,
    locale: UserLanguage = UserLanguage.EN,
) -> None:
    tx_ref = callback.data.split(":", 2)[2]
    await callback.answer(t("payment.checking_toast", locale))

    outcome, message, _telegram_id = await finalize_chapa_payment(session, tx_ref)
    if outcome in (FulfillOutcome.CREDITED, FulfillOutcome.ALREADY_DONE):
        await state.clear()
    await callback.message.edit_text(message)


# ── Wallet top-up entry point ────────────────────────────────────────────────
# ponytail: lives here (not wallet.py) because once "top up" is tapped, every
# remaining step — amount entry, Chapa/Bank choice, receipt/verify — is this
# file's existing machinery. Splitting the entry point into a different file
# from the flow it triggers would be the arbitrary kind of multi-file, not
# the helpful kind.

@router.callback_query(F.data == "pay:wallet_topup")
async def start_wallet_topup(callback: CallbackQuery, state: FSMContext, locale: UserLanguage = UserLanguage.EN) -> None:
    if not settings.WALLET_TOPUP_ENABLED:
        await callback.answer(t("payment.topup_disabled", locale), show_alert=True)
        return
    await callback.answer()
    await state.set_state(PaymentStates.entering_topup_amount)
    await callback.message.edit_text(t("payment.topup_prompt", locale))


@router.message(PaymentStates.entering_topup_amount)
async def handle_topup_amount(
    message: Message, session: AsyncSession, state: FSMContext,
    locale: UserLanguage = UserLanguage.EN,
) -> None:
    try:
        amount = float(message.text.strip())
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer(t("payment.topup_invalid", locale))
        return

    await state.update_data(topup_amount=amount)
    await state.set_state(PaymentStates.selecting_method)

    await _send_payment_methods(
        message, session, locale,
        t("payment.topup_method_prompt", locale, amount=f"{amount:.0f}"),
        wallet_balance=0,  # can't fund the wallet from the wallet itself
    )


# ── Pay VIP plan from existing wallet balance ────────────────────────────────

async def _pay_vip_from_wallet(session: AsyncSession, state: FSMContext, user, locale: UserLanguage) -> tuple[str, float] | str:
    """(success_text, new_balance) or a plain error string. Shared by the
    inline-callback and reply-keyboard entry points — the deduction and
    subscription activation happen exactly once, here."""
    plan = await _selected_plan(state)
    sub_svc = SubscriptionService(session)
    amount = await sub_svc.get_price(plan)

    wallet_svc = WalletService(session)
    if not wallet_svc.can_afford(user, amount):
        return t("payment.insufficient_balance", locale, amount=f"{amount:.0f}")

    success, new_balance, payment = await wallet_svc.deduct(user, amount, payment_type=PaymentType.VIP, plan=plan.value)
    if not success or payment is None:
        return t("payment.deduction_failed", locale)

    sub = await sub_svc.activate(user, plan, payment_id=payment.id)
    return format_vip_granted((sub.expires_at - sub.started_at).days, sub.expires_at, locale=locale), new_balance


@router.callback_query(F.data == "pay:wallet", PaymentStates.selecting_method)
async def handle_wallet_payment(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession,
    locale: UserLanguage = UserLanguage.EN,
) -> None:
    user = await UserService(session).get_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer(t("payment.start_first", locale), show_alert=True)
        return
    locale = user.language

    result = await _pay_vip_from_wallet(session, state, user, locale)
    if isinstance(result, str):
        await callback.answer(result, show_alert=True)
        return
    text, new_balance = result
    await state.clear()
    await callback.answer(t("payment.paid_from_wallet_toast", locale, balance=f"{new_balance:.2f}"), show_alert=True)
    await callback.message.edit_text(text)


@router.message(TextKeyMatch("payment.wallet_button"), PaymentStates.selecting_method)
async def handle_wallet_payment_reply(
    message: Message, state: FSMContext, session: AsyncSession, locale: UserLanguage = UserLanguage.EN,
) -> None:
    user = await UserService(session).get_by_telegram_id(message.from_user.id)
    if not user:
        await message.answer(t("payment.start_first", locale))
        return
    locale = user.language

    result = await _pay_vip_from_wallet(session, state, user, locale)
    if isinstance(result, str):
        await message.answer(result)
        return
    text, new_balance = result
    await state.clear()
    await message.answer(t("payment.paid_from_wallet_toast", locale, balance=f"{new_balance:.2f}"))
    await message.answer(text)
