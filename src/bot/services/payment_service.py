from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models.payment import Payment, PaymentGateway, PaymentStatus, PaymentType


class PaymentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        user_id: int,
        amount: float,
        gateway: PaymentGateway,
        payment_type: PaymentType,
        plan: str | None = None,
        reference: str | None = None,
    ) -> Payment:
        p = Payment(
            user_id=user_id,
            amount=amount,
            gateway=gateway,
            payment_type=payment_type,
            plan=plan,
            reference=reference,
        )
        self.session.add(p)
        await self.session.flush()
        return p

    async def attach_receipt(self, payment_id: int, file_id: str) -> bool:
        p = await self.session.get(Payment, payment_id)
        if not p:
            return False
        p.receipt_file_id = file_id
        return True

    async def approve(self, payment_id: int) -> Payment | None:
        p = await self.session.get(Payment, payment_id)
        if not p:
            return None
        p.status = PaymentStatus.APPROVED
        p.resolved_at = datetime.now(timezone.utc)
        return p

    async def try_claim_pending(self, payment_id: int) -> bool:
        """
        Atomically flips a PENDING payment to APPROVED, but only if it's
        still PENDING. Returns False if someone else already claimed it.

        ponytail: exists specifically for Chapa, where both the webhook and
        the user's manual "Verify" tap can race to finalize the same
        tx_ref. A plain read-then-write (the shape approve()/reject() use)
        would let both callers pass a stale PENDING check and grant
        VIP/wallet credit twice. The WHERE clause makes the DB itself the
        arbiter of "who got there first" — a Python-side check can't
        guarantee that once two independent request paths are involved.
        """
        result = await self.session.execute(
            update(Payment)
            .where(Payment.id == payment_id, Payment.status == PaymentStatus.PENDING)
            .values(status=PaymentStatus.APPROVED, resolved_at=datetime.now(timezone.utc))
        )
        return result.rowcount == 1

    async def reject(self, payment_id: int, note: str = "") -> Payment | None:
        p = await self.session.get(Payment, payment_id)
        if not p:
            return None
        p.status = PaymentStatus.REJECTED
        p.rejection_note = note
        p.resolved_at = datetime.now(timezone.utc)
        return p

    async def get_pending(self) -> list[Payment]:
        result = await self.session.execute(
            select(Payment)
            .where(Payment.status == PaymentStatus.PENDING)
            .where(Payment.receipt_file_id.isnot(None))
            .order_by(Payment.created_at)
        )
        return list(result.scalars().all())

    async def get_by_id(self, payment_id: int) -> Payment | None:
        return await self.session.get(Payment, payment_id)

    async def get_by_reference(self, reference: str) -> Payment | None:
        result = await self.session.execute(
            select(Payment).where(Payment.reference == reference)
        )
        return result.scalar_one_or_none()

    async def get_user_payments(self, user_id: int) -> list[Payment]:
        result = await self.session.execute(
            select(Payment)
            .where(Payment.user_id == user_id)
            .order_by(Payment.created_at.desc())
        )
        return list(result.scalars().all())
