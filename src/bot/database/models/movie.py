from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Boolean, Enum, Float, Integer, String, Text, func
from bot.database.types import UTCDateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.database.base import Base


class MovieFileType(str, enum.Enum):
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"


class Movie(Base):
    __tablename__ = "movies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # Telegram file_id for the actual media (document/video/audio)
    file_id: Mapped[str] = mapped_column(String(256), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Which Telegram send_* method this file needs. DOCUMENT is the safe
    # default for pre-existing rows — every file was always delivered via
    # answer_document regardless of how it was originally uploaded, so this
    # default reproduces existing behaviour exactly for old data. Only newly
    # ingested files (post-fix) get an accurate VIDEO/AUDIO value.
    file_type: Mapped[MovieFileType] = mapped_column(
        Enum(MovieFileType), default=MovieFileType.DOCUMENT, nullable=False
    )
    # 0.0 = free to search; > 0 = PPV (Pay-Per-View) price in local currency
    ppv_price: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_broken: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # ISO date string of when this was scheduled, if any
    scheduled_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), nullable=False
    )

    watchlist_entries: Mapped[list["Watchlist"]] = relationship(  # noqa: F821
        back_populates="movie", cascade="all, delete-orphan"
    )

    @property
    def is_ppv(self) -> bool:
        return self.ppv_price > 0

    def __repr__(self) -> str:
        return f"<Movie id={self.id} title={self.title!r} ppv={self.ppv_price}>"
