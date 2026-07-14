from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models.channel import Channel, ChannelCategory


class ChannelService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_all(self) -> list[Channel]:
        result = await self.session.execute(
            select(Channel).order_by(Channel.display_order, Channel.id)
        )
        return list(result.scalars().all())

    async def get_by_category(self, category: ChannelCategory) -> list[Channel]:
        result = await self.session.execute(
            select(Channel)
            .where(Channel.category == category)
            .order_by(Channel.display_order, Channel.id)
        )
        return list(result.scalars().all())

    async def get_by_id(self, id: int) -> Channel | None:
        return await self.session.get(Channel, id)

    async def add(
        self,
        name: str,
        url: str,
        category: ChannelCategory,
        channel_id: int | None = None,
        force_join: bool = False,
    ) -> Channel:
        ch = Channel(name=name, url=url, category=category,
                     channel_id=channel_id, force_join=force_join)
        self.session.add(ch)
        await self.session.flush()
        return ch

    async def update(self, id: int, **kwargs) -> bool:
        ch = await self.get_by_id(id)
        if not ch:
            return False
        for key, val in kwargs.items():
            if hasattr(ch, key):
                setattr(ch, key, val)
        return True

    async def delete(self, id: int) -> bool:
        ch = await self.get_by_id(id)
        if not ch:
            return False
        await self.session.delete(ch)
        return True

    async def get_force_join_channels(self) -> list[Channel]:
        result = await self.session.execute(
            select(Channel).where(Channel.force_join.is_(True))
        )
        return list(result.scalars().all())

    async def set_force_join(self, channel_id: int, enabled: bool) -> bool:
        return await self.update(channel_id, force_join=enabled)

    async def get_trending_sources(self) -> list[Channel]:
        result = await self.session.execute(
            select(Channel).where(Channel.is_trending_source.is_(True))
        )
        return list(result.scalars().all())

    async def get_auto_index_sources(self) -> list[Channel]:
        result = await self.session.execute(
            select(Channel).where(Channel.is_auto_index_source.is_(True))
        )
        return list(result.scalars().all())
