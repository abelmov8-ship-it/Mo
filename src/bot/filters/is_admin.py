from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery

from bot.config import settings


class IsAdmin(BaseFilter):
    """Passes only if the update originates from a configured admin user."""

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user = event.from_user
        if user is None:
            return False
        return user.id in settings.ADMIN_IDS
