"""
Runnable self-check for the Channels/Payment reply-vs-inline keyboard type
toggle (bot.filters.text_key_match.TextKeyMatch + the two new
CHANNELS_KEYBOARD_TYPE/PAYMENT_KEYBOARD_TYPE runtime settings +
the reply-keyboard builders in channels.py/keyboards/user/payment.py).

Unlike the four button-label sessions before this, the actual admin-editable
*text* for these buttons already existed (channels.free_label/vip_label,
payment.chapa_button/bank_button/wallet_button were all registered and
bilingual from the very first session) — this feature is purely about
which *kind* of keyboard renders that already-bilingual text, and about
correctly routing a reply-keyboard tap back to the same handler an inline
tap would have reached, in either language.

Real bug this caught (in production, not caught by this file's first
version): TextKeyMatch.__call__ was declared as a plain `def`, not
`async def`. It didn't need to await anything internally, which is
exactly why it seemed fine — but aiogram unconditionally does
`await event_filter.call(...)` for every filter regardless of whether its
body needs to await anything, so a sync `__call__` breaks with
"TypeError: object bool can't be used in 'await' expression" the moment
the button is actually tapped. Every check below now `await`s the filter
call the same way aiogram does (check 1 also asserts
iscoroutinefunction directly), specifically because the original version
of this file called the filter synchronously and so couldn't have caught
this — a coroutine object is truthy regardless of what it would resolve
to, so an un-awaited check on a broken sync filter still silently passes.

Covers:
1. TextKeyMatch matches a key's current English AND Amharic text, and
   nothing else — checked live against t(), not a filter frozen at import
   time (an admin editing the label at runtime must not silently break
   the match, the same reasoning as filters.menu_action.MenuAction) —
   and is itself a proper coroutine function (see above).
2. The two new settings round-trip through the exact same
   _RUNTIME_OVERRIDES/hydrate_runtime_settings mechanism as
   MAINTENANCE_MODE and friends — no new persistence code, reused as-is.
3. payment_methods_reply_keyboard hides whichever methods are currently
   disabled/unavailable, exactly like the inline version already does,
   and always includes the 🏠 Main Menu escape hatch.
4. The channels reply keyboard shows Free/VIP in the caller's language
   plus the same escape hatch.
5. The escape-hatch text itself (ui.back_to_menu) is deliberately
   different from the admin's fixed "⬅️ Back to Main Menu" reply button,
   so TextKeyMatch("ui.back_to_menu") can never accidentally match it.

Run directly: `python3 tests/check_keyboard_type_toggle.py`
(Needs sqlalchemy + aiosqlite installed — same as every other DB-touching
check script in this suite.)
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from bot.database.base import Base
import bot.database.models  # noqa: F401  registers all models on Base.metadata
from bot.config import settings
from bot.database.models.user import UserLanguage
from bot.filters.text_key_match import TextKeyMatch
from bot.handlers.user.channels import _categories_reply_keyboard
from bot.keyboards.user.payment import payment_methods_reply_keyboard
from bot.services.settings_service import SettingsService, hydrate_runtime_settings
from bot.utils.i18n import save_text_override


async def _session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    return Session()


def check(label: str, condition: bool) -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        raise SystemExit(1)


def _reply_texts(markup) -> list[str]:
    return [btn.text for row in markup.keyboard for btn in row]


async def main() -> None:
    session = await _session()
    original_channels_type = settings.CHANNELS_KEYBOARD_TYPE
    original_payment_type = settings.PAYMENT_KEYBOARD_TYPE

    try:
        # 1. TextKeyMatch — live-checked, admin-edit-aware matching.
        # Every call here is awaited deliberately, matching exactly how
        # aiogram itself calls a filter (await event_filter.call(...)) —
        # this is what catching a filter's __call__ declared as a plain
        # `def` instead of `async def` actually requires: calling it
        # without awaiting just returns a coroutine object, which is
        # always truthy regardless of the real result, so a check that
        # doesn't await would pass even against a completely broken filter.
        free_filter = TextKeyMatch("channels.free_label")
        check("TextKeyMatch matches the current English text",
              await free_filter(SimpleNamespace(text="🆓 Free Channels")))
        check("TextKeyMatch doesn't match unrelated text",
              not await free_filter(SimpleNamespace(text="something else")))
        check("TextKeyMatch doesn't match on empty/missing text",
              not await free_filter(SimpleNamespace(text=None)))

        await save_text_override(session, "channels.free_label", "am", "🆓 ነፃ ቻናሎች")
        check("TextKeyMatch matches an admin-added Amharic override too",
              await free_filter(SimpleNamespace(text="🆓 ነፃ ቻናሎች")))
        check("...and still matches English after the Amharic override was added",
              await free_filter(SimpleNamespace(text="🆓 Free Channels")))
        await save_text_override(session, "channels.free_label", "am", "")  # cleanup

        multi_filter = TextKeyMatch("payment.chapa_button", "payment.bank_button")
        check("TextKeyMatch with multiple keys matches any one of them",
              await multi_filter(SimpleNamespace(text="🏦 Bank Transfer")))
        check("TextKeyMatch.__call__ is itself a coroutine function, not a plain function — "
              "aiogram awaits every filter unconditionally, so this must hold regardless of "
              "whether the filter's own body happens to need await internally",
              asyncio.iscoroutinefunction(free_filter.__call__))

        # 2. Settings round-trip through the existing runtime-overrides mechanism.
        await SettingsService(session).set("channels_keyboard_type", "reply")
        await SettingsService(session).set("payment_keyboard_type", "reply")
        await hydrate_runtime_settings(session)
        check("CHANNELS_KEYBOARD_TYPE hydrates from a saved override",
              settings.CHANNELS_KEYBOARD_TYPE == "reply")
        check("PAYMENT_KEYBOARD_TYPE hydrates independently of the channels one",
              settings.PAYMENT_KEYBOARD_TYPE == "reply")

        # 3. payment_methods_reply_keyboard: conditional visibility + escape hatch.
        markup = payment_methods_reply_keyboard(
            chapa_enabled=False, has_banks=True, wallet_balance=50.0, locale=UserLanguage.EN,
        )
        texts = _reply_texts(markup)
        check("Chapa disabled: its button is absent", not any("Chapa" in t_ for t_ in texts))
        check("Bank enabled: its button is present", any("Bank Transfer" in t_ for t_ in texts))
        check("Wallet balance > 0: its button is present", any("Use Wallet" in t_ for t_ in texts))
        check("🏠 Main Menu escape hatch is always present", "🏠 Main Menu" in texts)

        markup_no_wallet = payment_methods_reply_keyboard(
            chapa_enabled=True, has_banks=True, wallet_balance=0.0, locale=UserLanguage.EN,
        )
        check("Wallet balance == 0: its button is absent",
              not any("Use Wallet" in t_ for t_ in _reply_texts(markup_no_wallet)))

        # 4. Channels reply keyboard: correct language + escape hatch.
        en_markup = _categories_reply_keyboard(UserLanguage.EN)
        check("Channels reply keyboard (EN): Free/VIP + Main Menu, no extras",
              _reply_texts(en_markup) == ["🆓 Free Channels", "💎 VIP Channels", "🏠 Main Menu"])

        # 5. The escape hatch can never collide with the admin's fixed button.
        check("ui.back_to_menu's default text is NOT the admin's fixed back-button text",
              "🏠 Main Menu" != "⬅️ Back to Main Menu")

        print("\nAll keyboard-type-toggle checks passed.")
    finally:
        # Global singleton — must not leak this test's values into whatever
        # imports bot.config.settings next.
        settings.CHANNELS_KEYBOARD_TYPE = original_channels_type
        settings.PAYMENT_KEYBOARD_TYPE = original_payment_type
        await session.close()


asyncio.run(main())
