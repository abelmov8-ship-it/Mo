from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, func
from bot.database.types import UTCDateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.database.base import Base


class Referral(Base):
    __tablename__ = "referrals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    # The unique token used in deep-link: t.me/bot?start=ref_{token}
    referral_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    invite_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Tracks how many VIP reward cycles have been given out
    rewards_claimed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="referral")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Referral user={self.user_id} code={self.referral_code!r} invites={self.invite_count}>"
