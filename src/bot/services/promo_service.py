from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models.promo_code import PromoCode, PromoCodeType
from bot.database.models.user import User
from bot.services.user_service import UserService
from bot.utils.i18n import t


class PromoService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(self) -> list[PromoCode]:
        result = await self.session.execute(
            select(PromoCode).order_by(PromoCode.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_id(self, promo_id: int) -> PromoCode | None:
        return await self.session.get(PromoCode, promo_id)

    async def get_by_code(self, code: str) -> PromoCode | None:
        result = await self.session.execute(
            select(PromoCode).where(PromoCode.code == code.strip().upper())
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        code: str,
        code_type: PromoCodeType,
        value: float,
        usage_limit: int | None = None,
        expires_at: datetime | None = None,
    ) -> PromoCode:
        promo = PromoCode(
            code=code.strip().upper(),
            code_type=code_type,
            value=value,
            usage_limit=usage_limit,
            expires_at=expires_at,
        )
        self.session.add(promo)
        await self.session.flush()
        return promo

    async def delete(self, promo_id: int) -> bool:
        promo = await self.get_by_id(promo_id)
        if not promo:
            return False
        await self.session.delete(promo)
        return True

    async def redeem(self, code: str, user: User) -> tuple[bool, str]:
        """Returns (success, user-facing message)."""
        promo = await self.get_by_code(code)
        if not promo:
            return False, t("promo.invalid", user.language)
        if promo.is_expired:
            return False, t("promo.expired", user.language)
        if promo.is_exhausted:
            return False, t("promo.exhausted", user.language)

        user_svc = UserService(self.session)
        if promo.code_type == PromoCodeType.VIP_DAYS:
            await user_svc.grant_vip(user, days=int(promo.value), plan="promo")
            msg = t("promo.redeemed_vip", user.language, days=int(promo.value))
        else:
            await user_svc.credit_wallet(user, promo.value)
            msg = t("promo.redeemed_wallet", user.language, amount=f"{promo.value:.2f}")

        promo.used_count += 1
        await self.session.flush()
        return True, msg
