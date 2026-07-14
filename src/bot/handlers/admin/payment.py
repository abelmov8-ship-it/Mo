from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models.payment import PaymentType
from bot.database.models.subscription import PlanDuration, PLAN_DAYS
from bot.filters.is_admin import IsAdmin
from bot.fsm.admin import AdminPaymentStates
from bot.keyboards.admin.payment import (
    bank_list_keyboard,
    chapa_settings_keyboard,
    payment_admin_keyboard,
    receipt_action_keyboard,
    wallet_settings_keyboard,
)
from bot.services.payment_service import PaymentService
from bot.services.settings_service import SettingsService
from bot.services.subscription_service import SubscriptionService
from bot.services.user_service import UserService
from bot.services.wallet_service import WalletService
from bot.utils.formatters import format_vip_granted
from bot.utils.i18n import t

router = Router(name="admin:payment")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


@router.message(F.text == "💳 Payments")
async def payments_menu(message: Message) -> None:
    await message.answer("💳 <b>Payment Management</b>", reply_markup=payment_admin_keyboard())


# ── Pending receipts ─────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_pay:pending")
async def show_pending(callback: CallbackQuery, session: AsyncSession) -> None:
    pending = await PaymentService(session).get_pending()
    await callback.answer()
    if not pending:
        await callback.message.answer("✅ No pending receipts.")
        return

    user_svc = UserService(session)
    for p in pending[:10]:
        user = await user_svc.get_by_id(p.user_id)
        caption = (
            f"💳 <b>Pending Receipt</b>\n\n"
            f"User: {user.first_name if user else '—'} "
            f"(<code>{user.telegram_id if user else p.user_id}</code>)\n"
            f"Amount: <b>{p.amount:.0f} Birr</b>\n"
            f"Plan: {p.plan or 'N/A'}"
        )
        if p.receipt_file_id:
            await callback.message.answer_photo(
                p.receipt_file_id, caption=caption, reply_markup=receipt_action_keyboard(p.id)
            )
        else:
            await callback.message.answer(caption, reply_markup=receipt_action_keyboard(p.id))


@router.callback_query(F.data.startswith("receipt:approve:"))
async def approve_receipt(callback: CallbackQuery, session: AsyncSession) -> None:
    payment_id = int(callback.data.split(":")[2])

    payment_svc = PaymentService(session)
    payment = await payment_svc.approve(payment_id)

    if not payment:
        await callback.answer("Payment not found.", show_alert=True)
        return

    user_svc = UserService(session)
    sub_svc = SubscriptionService(session)
    user = await user_svc.get_by_id(payment.user_id)

    if user and payment.payment_type == PaymentType.WALLET_TOPUP:
        new_balance = await WalletService(session).top_up(user, payment.amount)
        try:
            await callback.bot.send_message(
                user.telegram_id,
                t("payment.wallet_topped_up", user.language, amount=f"{payment.amount:.0f}", balance=f"{new_balance:.2f}"),
            )
        except Exception:
            pass
    elif user and payment.plan:
        try:
            plan = PlanDuration(payment.plan)
            sub = await sub_svc.activate(user, plan, payment_id=payment.id)
            days = (sub.expires_at - sub.started_at).days
            try:
                await callback.bot.send_message(
                    user.telegram_id,
                    format_vip_granted(days, sub.expires_at, locale=user.language),
                )
            except Exception:
                pass
        except ValueError:
            pass

    if callback.message.caption is not None:
        await callback.message.edit_caption(
            caption=(callback.message.caption or "") + "\n\n✅ <b>APPROVED</b>",
            reply_markup=None,
        )
    else:
        await callback.message.edit_text(
            (callback.message.text or "") + "\n\n✅ <b>APPROVED</b>",
            reply_markup=None,
        )
    await callback.answer("✅ Payment approved and VIP granted.")


@router.callback_query(F.data.startswith("receipt:reject:"))
async def reject_receipt(callback: CallbackQuery, session: AsyncSession) -> None:
    payment_id = int(callback.data.split(":")[2])

    payment_svc = PaymentService(session)
    payment = await payment_svc.reject(payment_id, note="Rejected by admin")

    if not payment:
        await callback.answer("Payment not found.", show_alert=True)
        return

    user_svc = UserService(session)
    user = await user_svc.get_by_id(payment.user_id)
    if user:
        try:
            await callback.bot.send_message(
                user.telegram_id,
                "❌ Your payment receipt was rejected. Please re-submit or contact support.",
            )
        except Exception:
            pass

    if callback.message.caption is not None:
        await callback.message.edit_caption(
            caption=(callback.message.caption or "") + "\n\n❌ <b>REJECTED</b>",
            reply_markup=None,
        )
    else:
        await callback.message.edit_text(
            (callback.message.text or "") + "\n\n❌ <b>REJECTED</b>",
            reply_markup=None,
        )
    await callback.answer("❌ Payment rejected.")


# ── Bank accounts ────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_pay:banks")
async def show_banks(callback: CallbackQuery, session: AsyncSession) -> None:
    banks = await SettingsService(session).get_banks()
    await callback.message.edit_text(
        f"🏦 <b>Bank Accounts</b> ({len(banks)})", reply_markup=bank_list_keyboard(banks)
    )
    await callback.answer()


@router.callback_query(F.data == "bank:add")
async def bank_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminPaymentStates.adding_bank_name)
    await callback.message.edit_text("Send the bank name:")
    await callback.answer()


@router.message(AdminPaymentStates.adding_bank_name)
async def bank_add_name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=message.text.strip())
    await state.set_state(AdminPaymentStates.adding_bank_account)
    await message.answer("Send the account number:")


@router.message(AdminPaymentStates.adding_bank_account)
async def bank_add_account(message: Message, state: FSMContext) -> None:
    await state.update_data(account=message.text.strip())
    await state.set_state(AdminPaymentStates.adding_bank_holder)
    await message.answer("Send the account holder name:")


@router.message(AdminPaymentStates.adding_bank_holder)
async def bank_add_holder(message: Message, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    settings_svc = SettingsService(session)
    await settings_svc.add_bank(name=data["name"], account=data["account"], holder=message.text.strip())
    await state.clear()
    banks = await settings_svc.get_banks()
    await message.answer(f"✅ Bank account added.", reply_markup=bank_list_keyboard(banks))


@router.callback_query(F.data.startswith("bank:edit:"))
async def bank_edit_menu(callback: CallbackQuery) -> None:
    bank_id = int(callback.data.split(":")[2])
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Name",    callback_data=f"bank:editfield:{bank_id}:name")
    builder.button(text="✏️ Account", callback_data=f"bank:editfield:{bank_id}:account")
    builder.button(text="✏️ Holder",  callback_data=f"bank:editfield:{bank_id}:holder")
    builder.button(text="⬅️ Back",    callback_data="admin_pay:banks")
    builder.adjust(1)
    await callback.message.edit_text("What would you like to edit?", reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("bank:editfield:"))
async def bank_edit_field_start(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, bank_id, field = callback.data.split(":")
    await state.update_data(bank_id=int(bank_id), field=field)
    await state.set_state(AdminPaymentStates.editing_bank)
    await callback.message.edit_text(f"Send the new {field}:")
    await callback.answer()


@router.message(AdminPaymentStates.editing_bank)
async def bank_edit_field_apply(message: Message, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    settings_svc = SettingsService(session)
    await settings_svc.update_bank(data["bank_id"], **{data["field"]: message.text.strip()})
    await state.clear()
    banks = await settings_svc.get_banks()
    await message.answer("✅ Updated.", reply_markup=bank_list_keyboard(banks))


@router.callback_query(F.data.startswith("bank:delete:"))
async def bank_delete(callback: CallbackQuery, session: AsyncSession) -> None:
    bank_id = int(callback.data.split(":")[2])
    settings_svc = SettingsService(session)
    deleted = await settings_svc.delete_bank(bank_id)
    banks = await settings_svc.get_banks()
    await callback.answer("✅ Deleted." if deleted else "Not found.", show_alert=True)
    await callback.message.edit_text(
        f"🏦 <b>Bank Accounts</b> ({len(banks)})", reply_markup=bank_list_keyboard(banks)
    )


# ── VIP Pricing ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_pay:pricing")
async def show_pricing(callback: CallbackQuery, session: AsyncSession) -> None:
    sub_svc = SubscriptionService(session)
    prices = await sub_svc.get_all_prices()
    builder = InlineKeyboardBuilder()
    for plan, price in prices.items():
        builder.button(text=f"{plan.value} — {price:.0f} Birr", callback_data=f"pricing:edit:{plan.value}")
    builder.adjust(1)
    await callback.message.edit_text("💎 <b>VIP Pricing</b>\nTap a plan to update its price:", reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("pricing:edit:"))
async def pricing_edit_start(callback: CallbackQuery, state: FSMContext) -> None:
    plan_val = callback.data.split(":")[2]
    await state.update_data(pricing_plan=plan_val)
    await state.set_state(AdminPaymentStates.updating_price)
    await callback.message.edit_text(f"Send the new price (Birr) for {plan_val}:")
    await callback.answer()


@router.message(AdminPaymentStates.updating_price)
async def save_price(message: Message, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    try:
        price = float(message.text.strip())
        if price < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Send a number ≥ 0.")
        return
    plan = PlanDuration(data["pricing_plan"])
    await SubscriptionService(session).set_price(plan, price)
    await state.clear()
    await message.answer(f"✅ {plan.value} price set to {price:.0f} Birr.")


# ── Chapa settings ───────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_pay:chapa")
async def show_chapa_settings(callback: CallbackQuery) -> None:
    from bot.config import settings
    webhook_url = (
        f"{settings.PUBLIC_BASE_URL}/webhooks/chapa"
        if settings.PUBLIC_BASE_URL
        else "⚠️ Set PUBLIC_BASE_URL in .env first"
    )
    await callback.message.edit_text(
        f"⚙️ <b>Chapa Settings</b>\n\n"
        f"Webhook URL (paste into Chapa dashboard → Webhooks):\n<code>{webhook_url}</code>",
        reply_markup=chapa_settings_keyboard(settings.CHAPA_ENABLED),
    )
    await callback.answer()


@router.callback_query(F.data == "admin:toggle_chapa")
async def toggle_chapa(callback: CallbackQuery, session: AsyncSession) -> None:
    from bot.config import settings
    settings.CHAPA_ENABLED = not settings.CHAPA_ENABLED
    await SettingsService(session).set_bool("chapa_enabled", settings.CHAPA_ENABLED)
    await callback.answer(f"Chapa: {'ON' if settings.CHAPA_ENABLED else 'OFF'}", show_alert=True)
    await callback.message.edit_reply_markup(
        reply_markup=chapa_settings_keyboard(settings.CHAPA_ENABLED)
    )


@router.callback_query(F.data == "admin:update_chapa_key")
async def update_chapa_key_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminPaymentStates.updating_chapa_key)
    await callback.message.answer("🔑 Send the new Chapa Secret Key:")
    await callback.answer()


@router.message(AdminPaymentStates.updating_chapa_key)
async def save_chapa_key(message: Message, session: AsyncSession, state: FSMContext) -> None:
    from bot.config import settings
    from pydantic import SecretStr
    new_key = message.text.strip()
    settings.CHAPA_SECRET_KEY = SecretStr(new_key)
    await SettingsService(session).set("chapa_secret_key", new_key)
    await message.answer(f"✅ Chapa key updated. ({new_key[:8]}…)")
    await state.clear()


@router.callback_query(F.data == "admin:update_chapa_webhook_secret")
async def update_chapa_webhook_secret_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminPaymentStates.updating_chapa_webhook_secret)
    await callback.message.answer(
        "🔐 Send the Webhook Secret you set in the Chapa dashboard (Settings → Webhooks):"
    )
    await callback.answer()


@router.message(AdminPaymentStates.updating_chapa_webhook_secret)
async def save_chapa_webhook_secret(message: Message, session: AsyncSession, state: FSMContext) -> None:
    from bot.config import settings
    from pydantic import SecretStr
    new_secret = message.text.strip()
    settings.CHAPA_WEBHOOK_SECRET = SecretStr(new_secret)
    await SettingsService(session).set("chapa_webhook_secret", new_secret)
    await message.answer("✅ Webhook secret updated. Automatic payment confirmations are now active.")
    await state.clear()


# ── Wallet settings ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_pay:wallet")
async def show_wallet_settings(callback: CallbackQuery) -> None:
    from bot.config import settings
    await callback.message.edit_text(
        "👛 <b>Wallet Settings</b>", reply_markup=wallet_settings_keyboard(settings.WALLET_TOPUP_ENABLED)
    )
    await callback.answer()


@router.callback_query(F.data == "admin:toggle_wallet_topup")
async def toggle_wallet_topup(callback: CallbackQuery, session: AsyncSession) -> None:
    from bot.config import settings
    settings.WALLET_TOPUP_ENABLED = not settings.WALLET_TOPUP_ENABLED
    await SettingsService(session).set_bool("wallet_topup_enabled", settings.WALLET_TOPUP_ENABLED)
    await callback.answer(f"Top-up: {'ON' if settings.WALLET_TOPUP_ENABLED else 'OFF'}", show_alert=True)
    await callback.message.edit_reply_markup(
        reply_markup=wallet_settings_keyboard(settings.WALLET_TOPUP_ENABLED)
    )
