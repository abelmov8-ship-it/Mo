from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models.menu_button import MenuButton, MenuButtonAction, MenuButtonType


class MenuButtonService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_all(self) -> list[MenuButton]:
        result = await self.session.execute(
            select(MenuButton).order_by(MenuButton.display_order, MenuButton.id)
        )
        return list(result.scalars().all())

    async def get_visible(self, keyboard_type: MenuButtonType) -> list[MenuButton]:
        result = await self.session.execute(
            select(MenuButton)
            .where(MenuButton.keyboard_type == keyboard_type)
            .where(MenuButton.is_visible.is_(True))
            .order_by(MenuButton.display_order, MenuButton.id)
        )
        return list(result.scalars().all())

    async def get_by_id(self, button_id: int) -> MenuButton | None:
        return await self.session.get(MenuButton, button_id)

    async def add(
        self,
        label: str,
        action: MenuButtonAction,
        keyboard_type: MenuButtonType = MenuButtonType.REPLY,
    ) -> MenuButton:
        result = await self.session.execute(select(func.max(MenuButton.display_order)))
        max_order = result.scalar_one_or_none()
        btn = MenuButton(
            label=label, action=action, keyboard_type=keyboard_type,
            display_order=(max_order if max_order is not None else -1) + 1,
        )
        self.session.add(btn)
        await self.session.flush()
        return btn

    async def update(self, button_id: int, **kwargs) -> bool:
        btn = await self.get_by_id(button_id)
        if not btn:
            return False
        for key, val in kwargs.items():
            if hasattr(btn, key):
                setattr(btn, key, val)
        return True

    async def delete(self, button_id: int) -> bool:
        btn = await self.get_by_id(button_id)
        if not btn:
            return False
        await self.session.delete(btn)
        return True

    async def move(self, button_id: int, direction: int) -> bool:
        """direction: -1 to move up, +1 to move down. Swaps display_order
        with whichever neighbour currently sits on that side — a plain
        adjacent-swap, not a full renumbering pass."""
        buttons = await self.get_all()
        idx = next((i for i, b in enumerate(buttons) if b.id == button_id), None)
        if idx is None:
            return False
        target = idx + direction
        if not (0 <= target < len(buttons)):
            return False
        buttons[idx].display_order, buttons[target].display_order = (
            buttons[target].display_order, buttons[idx].display_order,
        )
        return True
