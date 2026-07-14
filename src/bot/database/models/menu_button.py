from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Boolean, Enum, Integer, String, func
from bot.database.types import UTCDateTime
from sqlalchemy.orm import Mapped, mapped_column

from bot.database.base import Base


class MenuButtonAction(str, enum.Enum):
    """The bot's fixed set of reachable top-level features. An admin composes
    the main menu out of these — they pick which feature a button opens and
    what it's labelled, not what it does. Keeping this a closed enum (rather
    than a free-form callback string) is what makes the 'rename without
    breaking the button' requirement possible: the action never changes on
    rename, only the label column does.

    Admin Panel deliberately has no action here — it stays a hardcoded,
    always-visible button (see keyboards/user/main_menu.py). Making an
    admin's only way into the admin panel itself hideable/deletable through
    the same panel is a self-lockout risk for one row of convenience.
    """
    SEARCH = "search"
    CHANNELS = "channels"
    TRENDING = "trending"
    REFERRAL = "referral"
    VIP_PACKAGE = "vip_package"
    PAYMENT = "payment"
    PHOTO_EDITOR = "photo_editor"
    PROFILE = "profile"
    LANGUAGE = "language"
    SUPPORT = "support"


class MenuButtonType(str, enum.Enum):
    REPLY = "reply"
    INLINE = "inline"


class MenuButton(Base):
    __tablename__ = "menu_buttons"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    label: Mapped[str] = mapped_column(String(64), nullable=False)
    label_am: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[MenuButtonAction] = mapped_column(Enum(MenuButtonAction), nullable=False)
    keyboard_type: Mapped[MenuButtonType] = mapped_column(
        Enum(MenuButtonType), default=MenuButtonType.REPLY, nullable=False
    )
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), nullable=False
    )

    def display_label(self, locale) -> str:
        """label_am if the admin set one and Amharic was asked for, else
        label — same optional/fallback shape as every other admin-editable
        text in this bot (bot.utils.i18n.t). Takes UserLanguage or a plain
        "en"/"am" string (not typed as UserLanguage to avoid importing the
        user model into the menu_button model just for this)."""
        lang = locale.value if hasattr(locale, "value") else str(locale)
        return self.label_am if (lang == "am" and self.label_am) else self.label

    def __repr__(self) -> str:
        return f"<MenuButton id={self.id} label={self.label!r} action={self.action}>"
