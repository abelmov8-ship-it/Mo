from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models.subscription import Subscription
from bot.database.models.user import User, UserLanguage


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Lookup / registration ─────────────────────────────────────────────────

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> User | None:
        return await self.session.get(User, user_id)

    async def get_or_create(
        self,
        telegram_id: int,
        first_name: str,
        username: str | None = None,
    ) -> tuple[User, bool]:
        """Returns (user, created). Thread-safe via SELECT then INSERT."""
        user = await self.get_by_telegram_id(telegram_id)
        if user:
            # Update mutable fields
            user.first_name = first_name
            user.username = username
            user.last_active = datetime.now(timezone.utc)
            return user, False

        user = User(
            telegram_id=telegram_id,
            first_name=first_name,
            username=username,
        )
        self.session.add(user)
        await self.session.flush()
        return user, True

    # ── Language ──────────────────────────────────────────────────────────────

    async def set_language(self, telegram_id: int, language: UserLanguage) -> None:
        user = await self.get_by_telegram_id(telegram_id)
        if user:
            user.language = language

    # ── VIP management ────────────────────────────────────────────────────────

    async def grant_vip(self, user: User, days: int, plan: str = "custom") -> Subscription:
        """
        Grants VIP access for *days* days.

        ponytail: delegates to SubscriptionService.extend(), which already
        stacks onto any existing active subscription instead of overwriting
        it (extending from the later of "now" or the current expiry). The
        old version here always granted from "now", so a repeat referral
        reward or promo redemption on an already-VIP user could silently
        produce a shorter subscription than the one already active.
        `plan` is accepted for caller-API compatibility but not stored —
        extend() doesn't track grant provenance, matching its existing
        behavior for every other caller.
        """
        from bot.services.subscription_service import SubscriptionService
        return await SubscriptionService(self.session).extend(user, days)

    async def revoke_vip(self, user: User) -> None:
        user.is_vip = False

    async def get_active_subscription(self, user: User) -> Subscription | None:
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            select(Subscription)
            .where(Subscription.user_id == user.id)
            .where(Subscription.expires_at > now)
            .order_by(Subscription.expires_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    # ── Wallet ────────────────────────────────────────────────────────────────

    async def credit_wallet(self, user: User, amount: float) -> None:
        user.wallet_balance = round(user.wallet_balance + amount, 2)

    async def debit_wallet(self, user: User, amount: float) -> bool:
        """Returns False if insufficient balance."""
        if user.wallet_balance < amount:
            return False
        user.wallet_balance = round(user.wallet_balance - amount, 2)
        return True

    # ── Ban / Unban ───────────────────────────────────────────────────────────

    async def ban(self, user: User) -> None:
        user.is_banned = True

    async def unban(self, user: User) -> None:
        user.is_banned = False

    # ── Analytics ─────────────────────────────────────────────────────────────

    async def count_total(self) -> int:
        result = await self.session.execute(select(func.count()).select_from(User))
        return result.scalar_one()

    async def count_vip(self) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(User).where(User.is_vip.is_(True))
        )
        return result.scalar_one()

    async def count_active_today(self) -> int:
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        result = await self.session.execute(
            select(func.count()).select_from(User).where(User.last_active >= today)
        )
        return result.scalar_one()

    async def get_all_by_segment(self, segment: str) -> list[User]:
        """segment: 'all' | 'vip' | 'banned'"""
        stmt = select(User)
        if segment == "vip":
            stmt = stmt.where(User.is_vip.is_(True))
        elif segment == "banned":
            stmt = stmt.where(User.is_banned.is_(True))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_all_active(self) -> list[User]:
        """Returns all non-banned users (for broadcasts)."""
        result = await self.session.execute(
            select(User).where(User.is_banned.is_(False))
        )
        return list(result.scalars().all())

    async def get_all_vip(self) -> list[User]:
        result = await self.session.execute(
            select(User).where(User.is_vip.is_(True)).where(User.is_banned.is_(False))
        )
        return list(result.scalars().all())

    async def get_expiring_soon(self, within_days: int) -> list[tuple[User, Subscription]]:
        """Returns (user, sub) pairs whose VIP expires within *within_days* days."""
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(days=within_days)
        result = await self.session.execute(
            select(User, Subscription)
            .join(Subscription, Subscription.user_id == User.id)
            .where(Subscription.expires_at > now)
            .where(Subscription.expires_at <= cutoff)
        )
        return list(result.all())
