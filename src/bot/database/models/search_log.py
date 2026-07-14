from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Enum, String, func
from bot.database.types import UTCDateTime
from sqlalchemy.orm import Mapped, mapped_column

from bot.database.base import Base


class SearchLogKind(str, enum.Enum):
    MISS = "miss"          # search yielded zero results
    REQUEST = "request"    # user tapped 📣 Request Movie for this query


class SearchLog(Base):
    """
    One row per zero-result search or movie request.

    ponytail: a single table with a `kind` column instead of two near-
    identical tables (MissingSearch / MovieRequest) — the spec treats
    them as one feed read from two angles (admin analytics vs. content
    pipeline), and they share every column.
    """

    __tablename__ = "search_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    query: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    kind: Mapped[SearchLogKind] = mapped_column(Enum(SearchLogKind), nullable=False)
    # Set True once a matching movie is uploaded and the user is notified
    notified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<SearchLog id={self.id} kind={self.kind} query={self.query!r}>"
