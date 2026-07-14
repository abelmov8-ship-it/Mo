from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, Integer, String, func
from bot.database.types import UTCDateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.database.base import Base


class PlanDuration(str, enum.Enum):
    ONE_WEEK = "1w"
    TWO_WEEKS = "2w"
    ONE_MONTH = "1m"
    THREE_MONTHS = "3m"
    SIX_MONTHS = "6m"
    ONE_YEAR = "1y"
    CUSTOM = "custom"       # granted manually by admin (X days)
    REFERRAL = "referral"   # earned via referral milestone


# Maps plan keys to their day count for pricing and expiry calculations
PLAN_DAYS: dict[PlanDuration, int] = {
    PlanDuration.ONE_WEEK: 7,
    PlanDuration.TWO_WEEKS: 14,
    PlanDuration.ONE_MONTH: 30,
    PlanDuration.THREE_MONTHS: 90,
    PlanDuration.SIX_MONTHS: 180,
    PlanDuration.ONE_YEAR: 365,
}


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    plan: Mapped[PlanDuration] = mapped_column(Enum(PlanDuration), nullable=False)
    # Days granted (used for CUSTOM and REFERRAL plans)
    custom_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    # The payment row that triggered this subscription, if applicable
    payment_id: Mapped[int | None] = mapped_column(
        ForeignKey("payments.id", ondelete="SET NULL"), nullable=True
    )

    user: Mapped["User"] = relationship(back_populates="subscriptions")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Subscription user={self.user_id} plan={self.plan} expires={self.expires_at}>"
