from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Enum, Float, Integer, String, func
from bot.database.types import UTCDateTime
from sqlalchemy.orm import Mapped, mapped_column

from bot.database.base import Base


class PromoCodeType(str, enum.Enum):
    VIP_DAYS = "vip_days"
    WALLET_CREDIT = "wallet_credit"


class PromoCode(Base):
    __tablename__ = "promo_codes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    code_type: Mapped[PromoCodeType] = mapped_column(Enum(PromoCodeType), nullable=False)
    # Days to grant (if VIP_DAYS) or amount to credit (if WALLET_CREDIT)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    usage_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)   # None = unlimited
    used_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), nullable=False
    )

    @property
    def is_exhausted(self) -> bool:
        return self.usage_limit is not None and self.used_count >= self.usage_limit

    @property
    def is_expired(self) -> bool:
        from datetime import timezone
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at

    @property
    def is_valid(self) -> bool:
        return not self.is_exhausted and not self.is_expired

    def __repr__(self) -> str:
        return f"<PromoCode code={self.code!r} type={self.code_type} value={self.value}>"
