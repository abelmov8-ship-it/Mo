from __future__ import annotations

import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database.models.referral import Referral
from bot.database.models.user import User


class ReferralService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create(self, user: User) -> Referral:
        result = await self.session.execute(
            select(Referral).where(Referral.user_id == user.id)
        )
        ref = result.scalar_one_or_none()
        if ref:
            return ref

        code = secrets.token_urlsafe(8)  # ~11 chars, URL-safe
        ref = Referral(user_id=user.id, referral_code=code)
        self.session.add(ref)
        await self.session.flush()
        return ref

    async def get_by_code(self, code: str) -> Referral | None:
        result = await self.session.execute(
            select(Referral).where(Referral.referral_code == code)
        )
        return result.scalar_one_or_none()

    async def record_invite(self, referrer_code: str) -> tuple[Referral, bool]:
        """
        Increments the invite counter for the given referrer code.
        Returns (referral, milestone_reached).
        """
        ref = await self.get_by_code(referrer_code)
        if not ref:
            return None, False  # type: ignore[return-value]

        ref.invite_count += 1
        milestone = settings.REFERRAL_MILESTONE

        # Check if a NEW milestone cycle has been completed
        current_cycles = ref.invite_count // milestone
        milestone_reached = current_cycles > ref.rewards_claimed

        if milestone_reached:
            ref.rewards_claimed = current_cycles

        await self.session.flush()
        return ref, milestone_reached

    def build_deep_link(self, bot_username: str, referral_code: str) -> str:
        return f"https://t.me/{bot_username}?start=ref_{referral_code}"
