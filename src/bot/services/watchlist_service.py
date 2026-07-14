from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models.movie import Movie
from bot.database.models.watchlist import Watchlist


class WatchlistService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_for_user(self, user_id: int) -> list[Movie]:
        result = await self.session.execute(
            select(Movie)
            .join(Watchlist, Watchlist.movie_id == Movie.id)
            .where(Watchlist.user_id == user_id)
            .order_by(Watchlist.added_at.desc())
        )
        return list(result.scalars().all())

    async def is_in_watchlist(self, user_id: int, movie_id: int) -> bool:
        result = await self.session.execute(
            select(Watchlist.id).where(Watchlist.user_id == user_id, Watchlist.movie_id == movie_id)
        )
        return result.scalar_one_or_none() is not None

    async def add(self, user_id: int, movie_id: int) -> bool:
        """Returns False (no-op) if already present — same duplicate-safe
        behavior add_to_watchlist already had inline, just centralized."""
        if await self.is_in_watchlist(user_id, movie_id):
            return False
        self.session.add(Watchlist(user_id=user_id, movie_id=movie_id))
        return True

    async def remove(self, user_id: int, movie_id: int) -> bool:
        result = await self.session.execute(
            select(Watchlist).where(Watchlist.user_id == user_id, Watchlist.movie_id == movie_id)
        )
        entry = result.scalar_one_or_none()
        if not entry:
            return False
        await self.session.delete(entry)
        return True
