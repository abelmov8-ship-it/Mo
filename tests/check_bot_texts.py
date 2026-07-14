"""
Runnable self-check for the generic bot-text override system
(bot.utils.i18n + SettingsService.get/set_text) — the DB-backed replacement
for the old fixed 5-string _STRINGS dict and the bespoke welcome_message_en/am
editor in handlers/admin/broadcast.py.

Covers:
1. No override -> t() returns the shipped default for the requested
   language, falling back to English if only English is shipped.
2. Setting only ONE language's override leaves the other language on its
   own existing fallback, untouched — the actual "optional, independent
   per language" requirement, not just that overrides work at all.
3. The override is actually persisted via SettingsService, not just held
   in the in-process cache.
4. Saving an empty string clears the override back to the shipped default,
   and removes the persisted row.
5. A malformed override (bad {placeholder}) doesn't raise — t() falls
   through to the next usable template instead of breaking the caller.
6. hydrate_bot_texts() loads persisted overrides from a real session into
   the live cache t() reads from.
7. The one-time welcome_message_en/am -> text:start.welcome:{lang}
   migration promotes a legacy value once, and is a no-op (doesn't
   re-run or duplicate anything) the second time.

Run directly: `python3 tests/check_bot_texts.py`
(Needs sqlalchemy + aiosqlite installed — same as every other DB-touching
check script in this suite.)
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from bot.database.base import Base
import bot.database.models  # noqa: F401  registers all models on Base.metadata
from bot.database.models.user import UserLanguage
from bot.services.settings_service import SettingsService
from bot.utils import i18n


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


async def main() -> None:
    session = await _session()
    i18n._overrides.clear()  # t() reads a live module-level cache; start clean

    # Throwaway registry keys so this doesn't depend on (or clobber) the
    # real _DEFAULTS content — one bilingual key, one English-only key,
    # since those are the two shapes every real key is one of.
    i18n._DEFAULTS["_test.bilingual"] = {"en": "Hello {name}", "am": "ሰላም {name}"}
    i18n._DEFAULTS["_test.en_only"] = {"en": "English only {name}"}

    try:
        # 1. No override -> shipped default
        check("bilingual key: EN default with no override",
              i18n.t("_test.bilingual", UserLanguage.EN, name="X") == "Hello X")
        check("bilingual key: AM default with no override",
              i18n.t("_test.bilingual", UserLanguage.AM, name="X") == "ሰላም X")
        check("English-only key: AM request falls back to the EN default",
              i18n.t("_test.en_only", UserLanguage.AM, name="X") == "English only X")

        # 2. Setting only one language leaves the other on its own fallback
        await i18n.save_text_override(session, "_test.bilingual", "en", "Hi there {name}")
        check("overriding EN only: EN now returns the override",
              i18n.t("_test.bilingual", UserLanguage.EN, name="X") == "Hi there X")
        check("overriding EN only: AM is untouched, still its own default",
              i18n.t("_test.bilingual", UserLanguage.AM, name="X") == "ሰላም X")

        await i18n.save_text_override(session, "_test.en_only", "am", "የአማርኛ ብቻ {name}")
        check("adding an AM override to an EN-only key: AM now returns it",
              i18n.t("_test.en_only", UserLanguage.AM, name="X") == "የአማርኛ ብቻ X")
        check("adding an AM override to an EN-only key: EN is untouched",
              i18n.t("_test.en_only", UserLanguage.EN, name="X") == "English only X")

        # 3. Actually persisted, not just cached in-process
        stored = await SettingsService(session).get_text("_test.bilingual", "en")
        check("override is actually persisted via SettingsService", stored == "Hi there {name}")

        # 4. Reset (empty string) clears back to default, and the row is gone
        await i18n.save_text_override(session, "_test.bilingual", "en", "")
        check("empty save clears the override back to the shipped default",
              i18n.t("_test.bilingual", UserLanguage.EN, name="X") == "Hello X")
        check("clearing also removes the persisted row",
              await SettingsService(session).get_text("_test.bilingual", "en") is None)

        # 5. Malformed override degrades to the default instead of raising
        await i18n.save_text_override(session, "_test.bilingual", "en", "Broken {nonexistent_placeholder}")
        result = i18n.t("_test.bilingual", UserLanguage.EN, name="X")
        check("malformed override doesn't raise, falls through to the default", result == "Hello X")
        await i18n.save_text_override(session, "_test.bilingual", "en", "")  # don't leak into test 6

        # 6. hydrate_bot_texts loads persisted overrides into a fresh cache
        await SettingsService(session).set_text("_test.hydrate_check", "en", "Loaded from DB")
        i18n._overrides.clear()
        await i18n.hydrate_bot_texts(session)
        check("hydrate_bot_texts loads a persisted override into the live cache",
              i18n.t("_test.hydrate_check", UserLanguage.EN) == "Loaded from DB")

        # 7. Legacy welcome_message_en -> text:start.welcome:en migration
        i18n._overrides.pop("start.welcome", None)
        await SettingsService(session).delete("text:start.welcome:en")
        await SettingsService(session).set("welcome_message_en", "Legacy welcome {first_name}")
        await i18n.hydrate_bot_texts(session)
        check("legacy welcome_message_en is promoted into start.welcome on hydrate",
              i18n.t("start.welcome", UserLanguage.EN, first_name="X") == "Legacy welcome X")
        check("legacy row is deleted once migrated",
              await SettingsService(session).get("welcome_message_en") is None)

        await i18n.hydrate_bot_texts(session)  # second run: nothing left to migrate
        check("running hydrate again doesn't touch or duplicate the migrated value",
              i18n.t("start.welcome", UserLanguage.EN, first_name="X") == "Legacy welcome X")
    finally:
        # Test-only registry/cache entries must not leak into any other
        # process that imports this module (there isn't one today, but a
        # module-level dict is exactly the kind of thing that outlives a
        # single test run if left uncleaned).
        i18n._DEFAULTS.pop("_test.bilingual", None)
        i18n._DEFAULTS.pop("_test.en_only", None)
        for k in ("_test.bilingual", "_test.en_only", "_test.hydrate_check"):
            i18n._overrides.pop(k, None)
        await session.close()

    print("\nAll bot-text override checks passed.")


asyncio.run(main())
