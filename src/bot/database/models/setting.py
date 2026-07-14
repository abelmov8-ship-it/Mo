from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from bot.database.base import Base


class Setting(Base):
    """
    Generic admin-editable key/value store.

    ponytail: one table for every "admin toggles this from chat" value
    (delete timer, maintenance mode, chapa key, bank accounts as JSON, …)
    instead of a bespoke column/model per setting. Values are stored as
    text; callers go through SettingsService for typed access. If this
    ever needs per-key validation or change history, that's the upgrade
    path — not a reason to add it now.
    """

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)

    def __repr__(self) -> str:
        return f"<Setting key={self.key!r}>"
