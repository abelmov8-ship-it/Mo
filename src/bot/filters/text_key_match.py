from __future__ import annotations

from aiogram.filters import BaseFilter
from aiogram.types import Message

from bot.utils.i18n import t


class TextKeyMatch(BaseFilter):
    """Matches a reply-keyboard button press against the CURRENT text of
    one or more bot.utils.i18n keys, in either language.

    Same reasoning as filters.menu_action.MenuAction: a reply-keyboard tap
    only ever sends back the button's visible text, and these keys are
    admin-editable at runtime via the Bot Texts panel — so a filter built
    once at router-registration time (e.g. F.text.in_({...})) would go
    stale the moment an admin edits the label. This checks t() fresh on
    every message instead, and needs no DB access to do it (unlike
    MenuAction) since t() already reads from the in-process cache.

    Give it one key when a button's identity IS the match (e.g. "did they
    tap Free Channels"); give it several when any one of them being tapped
    means "leave this screen" (e.g. every payment method's Cancel/Back).
    """

    def __init__(self, *keys: str) -> None:
        self.keys = keys

    async def __call__(self, message: Message) -> bool:
        if not message.text:
            return False
        return message.text in {t(key, lang) for key in self.keys for lang in ("en", "am")}
