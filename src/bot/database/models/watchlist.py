from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, UniqueConstraint, func
from bot.database.types import UTCDateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.database.base import Base


class Watchlist(Base):
    __tablename__ = "watchlist"
    __table_args__ = (
        UniqueConstraint("user_id", "movie_id", name="uq_watchlist_user_movie"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    movie_id: Mapped[int] = mapped_column(ForeignKey("movies.id", ondelete="CASCADE"), nullable=False)
    added_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="watchlist")   # noqa: F821
    movie: Mapped["Movie"] = relationship(back_populates="watchlist_entries")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Watchlist user={self.user_id} movie={self.movie_id}>"
