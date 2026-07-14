from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, func
from bot.database.types import UTCDateTime
from sqlalchemy.orm import Mapped, mapped_column

from bot.database.base import Base


class TrendingPoster(Base):
    """A single admin-curated poster/image shown in Trending & New. This is
    deliberately NOT a Movie — there is no file_id for an actual video or
    document anywhere on this model, because this section must never be
    able to deliver a file, only display an image. source_channel_id
    records which admin-approved channel the poster was forwarded from,
    for audit purposes; nullable + SET NULL on delete so removing a channel
    later doesn't destroy the historical record of what was shown."""

    __tablename__ = "trending_posters"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    image_file_id: Mapped[str] = mapped_column(String(256), nullable=False)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_channel_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("channels.id", ondelete="SET NULL"), nullable=True
    )
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<TrendingPoster id={self.id} source_channel_id={self.source_channel_id}>"
