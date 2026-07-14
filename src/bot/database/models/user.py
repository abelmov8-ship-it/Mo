from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Enum, Float, String, func
from bot.database.types import UTCDateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.database.base import Base


class UserLanguage(str, enum.Enum):
    EN = "en"
    AM = "am"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str] = mapped_column(String(64), nullable=False)
    language: Mapped[UserLanguage] = mapped_column(
        Enum(UserLanguage), default=UserLanguage.EN, nullable=False
    )
    wallet_balance: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    is_vip: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), nullable=False
    )
    last_active: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    subscriptions: Mapped[list["Subscription"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )
    payments: Mapped[list["Payment"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )
    referral: Mapped["Referral | None"] = relationship(  # noqa: F821
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    watchlist: Mapped[list["Watchlist"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} telegram_id={self.telegram_id} vip={self.is_vip}>"
