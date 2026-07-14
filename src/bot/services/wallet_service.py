from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models.user import User
from bot.services.payment_service import PaymentService
from bot.database.models.payment import Payment, PaymentGateway, PaymentType


class WalletService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def top_up(self, user: User, amount: float) -> float:
        """Credits the wallet and returns the new balance."""
        user.wallet_balance = round(user.wallet_balance + amount, 2)
        return user.wallet_balance

    async def deduct(
        self,
        user: User,
        amount: float,
        payment_type: PaymentType = PaymentType.PPV,
        plan: str | None = None,
    ) -> tuple[bool, float, Payment | None]:
        """
        Attempts to deduct *amount* from the wallet.
        Returns (success, new_balance, payment_row). payment_row is the
        already-approved internal Payment record on success, or None.
        """
        if user.wallet_balance < amount:
            return False, user.wallet_balance, None
        user.wallet_balance = round(user.wallet_balance - amount, 2)
        # Log as an internal wallet payment
        payment_svc = PaymentService(self.session)
        p = await payment_svc.create(
            user_id=user.id,
            amount=amount,
            gateway=PaymentGateway.WALLET,
            payment_type=payment_type,
            plan=plan,
        )
        from bot.database.models.payment import PaymentStatus
        p.status = PaymentStatus.APPROVED
        return True, user.wallet_balance, p

    def can_afford(self, user: User, amount: float) -> bool:
        return user.wallet_balance >= amount
