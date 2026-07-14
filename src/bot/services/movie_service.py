from __future__ import annotations

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models.movie import Movie, MovieFileType


class MovieService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def search(self, query: str, limit: int = 10) -> list[Movie]:
        """Full-text-style LIKE search on title."""
        pattern = f"%{query.strip()}%"
        result = await self.session.execute(
            select(Movie)
            .where(Movie.title.ilike(pattern))
            .where(Movie.is_broken.is_(False))
            .order_by(Movie.view_count.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_id(self, movie_id: int) -> Movie | None:
        return await self.session.get(Movie, movie_id)

    async def get_by_file_id(self, file_id: str) -> Movie | None:
        result = await self.session.execute(
            select(Movie).where(Movie.file_id == file_id)
        )
        return result.scalar_one_or_none()

    async def add(
        self,
        file_id: str,
        title: str,
        ppv_price: float = 0.0,
        file_type: MovieFileType = MovieFileType.DOCUMENT,
    ) -> Movie:
        movie = Movie(file_id=file_id, title=title, ppv_price=ppv_price, file_type=file_type)
        self.session.add(movie)
        await self.session.flush()
        return movie

    async def batch_add(self, entries: list[dict]) -> list[Movie]:
        """
        entries: list of {"file_id": str, "title": str, "ppv_price": float,
                           "file_type": MovieFileType}
        Skips entries whose file_id already exists.
        """
        added: list[Movie] = []
        for entry in entries:
            existing = await self.get_by_file_id(entry["file_id"])
            if existing:
                continue
            movie = await self.add(
                file_id=entry["file_id"],
                title=entry["title"],
                ppv_price=entry.get("ppv_price", 0.0),
                file_type=entry.get("file_type", MovieFileType.DOCUMENT),
            )
            added.append(movie)
        return added

    async def update_title(self, movie_id: int, title: str) -> bool:
        movie = await self.get_by_id(movie_id)
        if not movie:
            return False
        movie.title = title
        return True

    async def update_file_id(
        self,
        movie_id: int,
        file_id: str,
        file_type: MovieFileType = MovieFileType.DOCUMENT,
    ) -> bool:
        movie = await self.get_by_id(movie_id)
        if not movie:
            return False
        movie.file_id = file_id
        movie.file_type = file_type
        movie.is_broken = False
        return True

    async def set_ppv_price(self, movie_id: int, price: float) -> bool:
        movie = await self.get_by_id(movie_id)
        if not movie:
            return False
        movie.ppv_price = max(0.0, price)
        return True

    async def mark_broken(self, movie_id: int) -> None:
        movie = await self.get_by_id(movie_id)
        if movie:
            movie.is_broken = True

    async def delete(self, movie_id: int) -> bool:
        movie = await self.get_by_id(movie_id)
        if not movie:
            return False
        await self.session.delete(movie)
        return True

    async def increment_view(self, movie_id: int) -> None:
        await self.session.execute(
            update(Movie)
            .where(Movie.id == movie_id)
            .values(view_count=Movie.view_count + 1)
        )

    async def get_broken(self) -> list[Movie]:
        result = await self.session.execute(
            select(Movie).where(Movie.is_broken.is_(True))
        )
        return list(result.scalars().all())
