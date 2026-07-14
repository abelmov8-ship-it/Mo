from __future__ import annotations

from aiogram.filters import BaseFilter
from aiogram.types import Message
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models.menu_button import MenuButton, MenuButtonAction, MenuButtonType


class MenuAction(BaseFilter):
    """Matches a reply-keyboard button press to a fixed action, independent
    of its current display label(s), in whichever language it was actually
    shown in — inline buttons don't need this (their callback_data already
    carries the action directly), but a reply-keyboard tap only ever sends
    back the button's visible text, and that text is label_am for an AM
    user with one set, label otherwise. Matching only `label` here would
    mean any button an admin gives an Amharic label never fires for the
    Amharic users it was renamed for."""

    def __init__(self, action: MenuButtonAction) -> None:
        self.action = action

    async def __call__(self, message: Message, session: AsyncSession) -> bool:
        if not message.text:
            return False
        result = await session.execute(
            select(MenuButton.id).where(
                MenuButton.action == self.action,
                MenuButton.keyboard_type == MenuButtonType.REPLY,
                MenuButton.is_visible.is_(True),
                or_(MenuButton.label == message.text, MenuButton.label_am == message.text),
            )
        )
        return result.scalar_one_or_none() is not None
