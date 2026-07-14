"""
Runnable self-check for bilingual main-menu button labels
(MenuButton.label_am + MenuButton.display_label + filters.menu_action.MenuAction).

Covers:
1. display_label(): label_am shown only when set AND Amharic is requested;
   every other combination falls back to label (the English/primary field).
2. MenuButtonService.update() can set AND clear label_am via its existing
   generic **kwargs mechanism — no changes needed there, but worth proving.
3. The MenuAction filter — which decides whether a reply-keyboard tap
   fires a given action — matches whichever label the user actually saw
   and tapped, English or Amharic. This was the real bug: before this fix,
   an Amharic-labelled button rendered correctly but tapping it did
   nothing, because the filter only ever checked the English label column.

Run directly: `python3 tests/check_menu_button_labels.py`
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
from bot.database.models.menu_button import MenuButton, MenuButtonAction, MenuButtonType
from bot.database.models.user import UserLanguage
from bot.filters.menu_action import MenuAction
from bot.services.menu_service import MenuButtonService


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
    svc = MenuButtonService(session)

    # 1. display_label() fallback shape
    btn = await svc.add("🔍 Search Movies", MenuButtonAction.SEARCH, MenuButtonType.REPLY)
    check("no label_am set: EN request shows the English label",
          btn.display_label(UserLanguage.EN) == "🔍 Search Movies")
    check("no label_am set: AM request falls back to the English label",
          btn.display_label(UserLanguage.AM) == "🔍 Search Movies")

    await svc.update(btn.id, label_am="🔍 ፊልም ይፈልጉ")
    await session.flush()
    check("label_am set: AM request now shows it",
          btn.display_label(UserLanguage.AM) == "🔍 ፊልም ይፈልጉ")
    check("label_am set: EN request is unaffected",
          btn.display_label(UserLanguage.EN) == "🔍 Search Movies")
    check("display_label also accepts a plain 'am' string, not just UserLanguage.AM",
          btn.display_label("am") == "🔍 ፊልም ይፈልጉ")

    # 2. Clearing label_am via the generic update() kwargs mechanism
    await svc.update(btn.id, label_am=None)
    await session.flush()
    check("clearing label_am reverts AM requests back to the English label",
          btn.display_label(UserLanguage.AM) == "🔍 Search Movies")

    # 3. The tap-matching filter — the actual bug this test exists to catch.
    await svc.update(btn.id, label_am="🔍 ፊልም ይፈልጉ")
    await session.flush()
    await session.commit()  # filter runs its own query against the DB, needs this committed

    action_filter = MenuAction(MenuButtonAction.SEARCH)
    matches_en = await action_filter(SimpleNamespace(text="🔍 Search Movies"), session)
    matches_am = await action_filter(SimpleNamespace(text="🔍 ፊልም ይፈልጉ"), session)
    matches_wrong = await action_filter(SimpleNamespace(text="something else entirely"), session)

    check("tapping the English-rendered button still matches its action", matches_en)
    check("tapping the Amharic-rendered button ALSO matches the same action "
          "(this is the bug: it silently didn't, before)", matches_am)
    check("unrelated text doesn't match", not matches_wrong)

    await session.close()
    print("\nAll menu-button bilingual-label checks passed.")


asyncio.run(main())
