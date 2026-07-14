from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Enum, Float, Integer, String, func
from bot.database.types import UTCDateTime
from sqlalchemy.orm import Mapped, mapped_column

from bot.database.base import Base


class ChannelCategory(str, enum.Enum):
    FREE = "free"
    VIP = "vip"


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    # Public @username or private invite URL
    url: Mapped[str] = mapped_column(String(256), nullable=False)
    # Telegram channel/group ID for membership checks and bot operations
    channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, unique=True)
    category: Mapped[ChannelCategory] = mapped_column(
        Enum(ChannelCategory), default=ChannelCategory.FREE, nullable=False
    )
    # When True, users must join this channel before using the bot
    force_join: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # When True, this channel is an admin-approved source for Trending & New
    # posters. Being a valid source is separate from force_join/category —
    # a channel can require joining AND be a poster source, or neither.
    is_trending_source: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # When True, any video/audio/document posted directly to this channel
    # is automatically indexed into the searchable movie catalog. Fully
    # independent of is_trending_source — a channel can be either, both,
    # or neither; they serve different features and were deliberately kept
    # as separate toggles rather than reusing one flag for both purposes.
    is_auto_index_source: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Per-channel PPV price override. None means "use the global
    # default_ppv_price setting"; a real number (including 0.0) means this
    # channel always gets that exact price regardless of the global
    # default. Kept nullable specifically so "no override" and "override
    # to free" are distinguishable — collapsing them onto a single 0.0
    # would make it impossible to tell "this channel is free" apart from
    # "this channel just hasn't been priced yet."
    custom_ppv_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Display order in the channel list
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<Channel id={self.id} name={self.name!r} category={self.category}>"
