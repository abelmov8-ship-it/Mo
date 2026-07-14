from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Enum, Float, ForeignKey, String, Text, func
from bot.database.types import UTCDateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.database.base import Base


class PaymentGateway(str, enum.Enum):
    CHAPA = "chapa"
    BANK = "bank"
    WALLET = "wallet"   # internal wallet deduction (PPV)


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class PaymentType(str, enum.Enum):
    VIP = "vip"
    WALLET_TOPUP = "wallet_topup"
    PPV = "ppv"


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    gateway: Mapped[PaymentGateway] = mapped_column(Enum(PaymentGateway), nullable=False)
    payment_type: Mapped[PaymentType] = mapped_column(Enum(PaymentType), nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus), default=PaymentStatus.PENDING, nullable=False
    )
    # Chapa transaction reference or bank transfer note. Unique (NULLs
    # excepted) so a webhook — an untrusted network caller — can never
    # cause two rows to claim the same Chapa tx_ref.
    reference: Mapped[str | None] = mapped_column(String(256), unique=True, nullable=True)
    # Telegram file_id of the receipt screenshot (bank transfers)
    receipt_file_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    # Admin rejection reason
    rejection_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Which VIP plan this payment is for (if payment_type == VIP)
    plan: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    # Set once the abandoned-payment-recovery job has nudged the user, so it
    # sends exactly one reminder per unpaid Chapa checkout instead of one
    # every time the job runs.
    reminder_sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    user: Mapped["User"] = relationship(back_populates="payments")  # noqa: F821

    def __repr__(self) -> str:
        return (
            f"<Payment id={self.id} user={self.user_id} "
            f"amount={self.amount} status={self.status}>"
        )
