from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models.subscription import PlanDuration, PLAN_DAYS, Subscription
from bot.database.models.user import User
from bot.services.settings_service import SettingsService


# Default VIP prices in ETB — used until an admin overrides them via
# Payment & Gateway Management -> VIP Pricing (persisted in the settings table).
DEFAULT_PRICES: dict[PlanDuration, float] = {
    PlanDuration.ONE_WEEK:     99.0,
    PlanDuration.TWO_WEEKS:    179.0,
    PlanDuration.ONE_MONTH:    299.0,
    PlanDuration.THREE_MONTHS: 799.0,
    PlanDuration.SIX_MONTHS:  1499.0,
    PlanDuration.ONE_YEAR:    2499.0,
}


def _stacked_expiry(now: datetime, days: int, existing_expiry: datetime | None) -> datetime:
    """
    The stacking rule shared by activate() and extend(): a new grant starts
    from whichever is later, "now" or any time already remaining, so a
    purchase/grant on top of an active subscription extends it instead of
    overwriting it with a shorter window. Pure function (no DB/async) so it
    can be checked directly — see check_subscription_math.py.
    """
    base = max(existing_expiry, now) if existing_expiry else now
    return base + timedelta(days=days)


class SubscriptionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def activate(
        self,
        user: User,
        plan: PlanDuration,
        payment_id: int | None = None,
    ) -> Subscription:
        days = PLAN_DAYS.get(plan, 30)
        now = datetime.now(timezone.utc)

        # ponytail: stacks onto any existing active subscription instead of
        # always starting a fresh count from "now". Without this, a user
        # who buys a new plan while VIP time remains gets a second,
        # shorter-expiry row that the active-subscription query silently
        # ignores in favor of the longer one already there — they paid but
        # gained nothing. See _stacked_expiry().
        existing = await self.get_active(user)
        expires = _stacked_expiry(now, days, existing.expires_at if existing else None)

        sub = Subscription(
            user_id=user.id,
            plan=plan,
            started_at=now,
            expires_at=expires,
            payment_id=payment_id,
        )
        self.session.add(sub)
        user.is_vip = True
        await self.session.flush()
        return sub

    async def extend(self, user: User, days: int) -> Subscription:
        """Extends an existing active sub, or creates a fresh one."""
        existing = await self.get_active(user)
        now = datetime.now(timezone.utc)

        if existing:
            existing.expires_at = _stacked_expiry(now, days, existing.expires_at)
            return existing

        sub = Subscription(
            user_id=user.id,
            plan=PlanDuration.CUSTOM,
            custom_days=days,
            started_at=now,
            expires_at=_stacked_expiry(now, days, None),
        )
        self.session.add(sub)
        user.is_vip = True
        await self.session.flush()
        return sub

    async def get_active(self, user: User) -> Subscription | None:
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            select(Subscription)
            .where(Subscription.user_id == user.id)
            .where(Subscription.expires_at > now)
            .order_by(Subscription.expires_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def expire_user(self, user: User) -> None:
        """Revokes VIP flag when subscription has expired."""
        active = await self.get_active(user)
        if not active:
            user.is_vip = False

    async def get_price(self, plan: PlanDuration) -> float:
        overrides = await SettingsService(self.session).get_json("vip_prices", {})
        return overrides.get(plan.value, DEFAULT_PRICES.get(plan, 0.0))

    async def get_all_prices(self) -> dict[PlanDuration, float]:
        overrides = await SettingsService(self.session).get_json("vip_prices", {})
        return {
            plan: overrides.get(plan.value, default)
            for plan, default in DEFAULT_PRICES.items()
        }

    async def set_price(self, plan: PlanDuration, amount: float) -> None:
        settings_svc = SettingsService(self.session)
        overrides = await settings_svc.get_json("vip_prices", {})
        overrides[plan.value] = amount
        await settings_svc.set_json("vip_prices", overrides)
