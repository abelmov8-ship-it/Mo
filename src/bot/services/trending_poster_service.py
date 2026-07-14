from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models.trending_poster import TrendingPoster


class TrendingPosterService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_all(self) -> list[TrendingPoster]:
        result = await self.session.execute(
            select(TrendingPoster).order_by(TrendingPoster.display_order, TrendingPoster.id)
        )
        return list(result.scalars().all())

    async def get_visible(self) -> list[TrendingPoster]:
        result = await self.session.execute(
            select(TrendingPoster)
            .where(TrendingPoster.is_visible.is_(True))
            .order_by(TrendingPoster.display_order, TrendingPoster.id)
        )
        return list(result.scalars().all())

    async def get_by_id(self, poster_id: int) -> TrendingPoster | None:
        return await self.session.get(TrendingPoster, poster_id)

    async def add(self, image_file_id: str, caption: str | None, source_channel_id: int | None) -> TrendingPoster:
        result = await self.session.execute(select(func.max(TrendingPoster.display_order)))
        max_order = result.scalar_one_or_none()
        poster = TrendingPoster(
            image_file_id=image_file_id, caption=caption, source_channel_id=source_channel_id,
            display_order=(max_order if max_order is not None else -1) + 1,
        )
        self.session.add(poster)
        await self.session.flush()
        return poster

    async def update(self, poster_id: int, **kwargs) -> bool:
        poster = await self.get_by_id(poster_id)
        if not poster:
            return False
        for key, val in kwargs.items():
            if hasattr(poster, key):
                setattr(poster, key, val)
        return True

    async def delete(self, poster_id: int) -> bool:
        poster = await self.get_by_id(poster_id)
        if not poster:
            return False
        await self.session.delete(poster)
        return True

    async def move(self, poster_id: int, direction: int) -> bool:
        posters = await self.get_all()
        idx = next((i for i, p in enumerate(posters) if p.id == poster_id), None)
        if idx is None:
            return False
        target = idx + direction
        if not (0 <= target < len(posters)):
            return False
        posters[idx].display_order, posters[target].display_order = (
            posters[target].display_order, posters[idx].display_order,
        )
        return True
