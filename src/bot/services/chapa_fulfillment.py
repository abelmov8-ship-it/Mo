from __future__ import annotations

import enum
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models.payment import PaymentStatus, PaymentType
from bot.database.models.subscription import PlanDuration
from bot.database.models.user import User, UserLanguage
from bot.services.chapa_service import ChapaError, ChapaService
from bot.services.payment_service import PaymentService
from bot.services.subscription_service import SubscriptionService
from bot.services.wallet_service import WalletService
from bot.utils.formatters import format_vip_granted
from bot.utils.i18n import t

logger = logging.getLogger(__name__)


class FulfillOutcome(str, enum.Enum):
    CREDITED = "credited"
    ALREADY_DONE = "already_done"
    NOT_FOUND = "not_found"
    VERIFY_FAILED = "verify_failed"


async def finalize_chapa_payment(
    session: AsyncSession, tx_ref: str
) -> tuple[FulfillOutcome, str, int | None]:
    """
    Verifies a Chapa transaction and grants VIP/wallet credit if it's real.

    Shared by the manual "I've Paid — Verify" button (handlers/user/payment.py)
    and the Chapa webhook (webapp.py) — the only two ways a Chapa payment
    gets confirmed. Both call Chapa's own verify endpoint before crediting
    (a webhook payload's claimed status is never trusted on its own), and
    both go through PaymentService.try_claim_pending so whichever call gets
    there first wins and the other sees ALREADY_DONE instead of granting
    credit twice.

    Returns (outcome, user-facing message, telegram_id or None). Doesn't
    commit — callers own the session/transaction, matching every other
    service in this package.
    """
    payment_svc = PaymentService(session)
    payment = await payment_svc.get_by_reference(tx_ref)
    if payment is None:
        logger.warning("Chapa finalize: no payment row for tx_ref=%s", tx_ref)
        return FulfillOutcome.NOT_FOUND, t("payment.not_found"), None

    # Fetched here — before claiming anything below, and before every other
    # branch — for two reasons: (1) claiming the row and only then
    # discovering there's no one to credit would leave it stuck
    # APPROVED-but-uncredited, since the caller commits regardless of what
    # this function returns; (2) every branch from here down can now
    # localize its message to this user instead of only the success path.
    user = await session.get(User, payment.user_id)
    if user is None:
        logger.warning("Chapa finalize: payment %d has no matching user %d.", payment.id, payment.user_id)
        return FulfillOutcome.NOT_FOUND, t("payment.account_not_found"), None
    locale = user.language

    if payment.status != PaymentStatus.PENDING:
        return FulfillOutcome.ALREADY_DONE, t("payment.already_confirmed", locale), None

    try:
        await ChapaService().verify_payment(tx_ref)
    except ChapaError:
        return FulfillOutcome.VERIFY_FAILED, t("payment.verify_pending", locale), None

    won = await payment_svc.try_claim_pending(payment.id)
    if not won:
        return FulfillOutcome.ALREADY_DONE, t("payment.already_confirmed", locale), None

    if payment.payment_type == PaymentType.WALLET_TOPUP:
        new_balance = await WalletService(session).top_up(user, payment.amount)
        message = t("payment.wallet_topped_up", locale, amount=f"{payment.amount:.0f}", balance=f"{new_balance:.2f}")
    else:
        plan = PlanDuration(payment.plan)
        sub = await SubscriptionService(session).activate(user, plan, payment_id=payment.id)
        message = format_vip_granted((sub.expires_at - sub.started_at).days, sub.expires_at, locale=locale)

    return FulfillOutcome.CREDITED, message, user.telegram_id
