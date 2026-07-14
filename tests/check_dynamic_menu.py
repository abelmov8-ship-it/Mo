"""
Runnable self-check for Phase 3 (dynamic main menu).

The single property this whole phase exists for: renaming a button's label
must not break what it does. Reply-keyboard taps only ever send back visible
text, so that's checked against a real DB, not asserted by inspection —
check_rename_survives_via_filter is the one that actually matters here.

Also covers: MenuButtonService CRUD + reorder round-tripping through a real
session, inline pagination math (page boundaries, empty state), and that
every MenuButtonAction has a dispatch-table entry in start.py (a silent
KeyError there would only surface the first time someone tapped a button
whose action was added to the enum but forgotten in the table).

Run directly: `python3 tests/check_dynamic_menu.py`
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.database.base import Base
import bot.database.models  # noqa: F401  registers all models on Base.metadata
from bot.database.models.menu_button import MenuButtonAction, MenuButtonType
from bot.filters.menu_action import MenuAction
from bot.keyboards.user.main_menu import inline_menu_keyboard, reply_menu_keyboard
from bot.services.menu_service import MenuButtonService


async def _fresh_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    return engine, Session()


async def check_rename_survives_via_filter():
    engine, session = await _fresh_session()
    svc = MenuButtonService(session)
    btn = await svc.add("🔍 Search Any Movie", MenuButtonAction.SEARCH, MenuButtonType.REPLY)
    await session.commit()

    is_search = MenuAction(MenuButtonAction.SEARCH)
    old_label_msg = SimpleNamespace(text="🔍 Search Any Movie")
    assert await is_search(old_label_msg, session) is True

    # The actual rename an admin would do through Edit Label.
    await svc.update(btn.id, label="🔎 አስስ ፊልም")
    await session.commit()

    renamed_msg = SimpleNamespace(text="🔎 አስስ ፊልም")
    stale_msg = SimpleNamespace(text="🔍 Search Any Movie")
    assert await is_search(renamed_msg, session) is True, "renamed label must still match its action"
    assert await is_search(stale_msg, session) is False, "old label must stop matching after rename"

    # A different action's filter must never match this button, renamed or not.
    is_trending = MenuAction(MenuButtonAction.TRENDING)
    assert await is_trending(renamed_msg, session) is False

    await engine.dispose()
    print("✓ rename survives: MenuAction tracks the action through a label edit, both directions")


async def check_hidden_button_does_not_match():
    engine, session = await _fresh_session()
    svc = MenuButtonService(session)
    btn = await svc.add("💎 VIP Package", MenuButtonAction.VIP_PACKAGE, MenuButtonType.REPLY)
    await session.commit()

    is_vip = MenuAction(MenuButtonAction.VIP_PACKAGE)
    msg = SimpleNamespace(text="💎 VIP Package")
    assert await is_vip(msg, session) is True

    await svc.update(btn.id, is_visible=False)
    await session.commit()
    assert await is_vip(msg, session) is False, "hidden buttons must not be reachable by their old text"

    await engine.dispose()
    print("✓ hiding a button removes it from the filter match, without deleting it")


async def check_crud_and_reorder():
    engine, session = await _fresh_session()
    svc = MenuButtonService(session)

    a = await svc.add("A", MenuButtonAction.SEARCH)
    b = await svc.add("B", MenuButtonAction.CHANNELS)
    c = await svc.add("C", MenuButtonAction.TRENDING)
    await session.commit()

    ordered = await svc.get_all()
    assert [x.label for x in ordered] == ["A", "B", "C"]

    await svc.move(c.id, -1)  # C moves up, should swap with B
    await session.commit()
    ordered = await svc.get_all()
    assert [x.label for x in ordered] == ["A", "C", "B"], f"got {[x.label for x in ordered]}"

    assert await svc.move(a.id, -1) is False, "moving the first item up must be a no-op, not an error"

    assert await svc.delete(b.id) is True
    assert await svc.delete(9999) is False
    remaining = await svc.get_all()
    assert len(remaining) == 2

    await engine.dispose()
    print("✓ MenuButtonService: add/get_all/move/delete round-trip correctly through a real session")


def check_inline_pagination_edges():
    def fake(n):
        return [SimpleNamespace(label=f"B{i}", action=SimpleNamespace(value="search")) for i in range(n)]

    assert inline_menu_keyboard([]) is None, "no buttons -> no keyboard, not an empty one"

    # Single page: no nav row at all.
    single = inline_menu_keyboard(fake(3), page=0)
    assert len(single.inline_keyboard) == 2  # 2+1, no nav row

    # A lone trailing content button on the last page must not merge into
    # the nav row (the bug caught and fixed while building this).
    last_page = inline_menu_keyboard(fake(9), page=1)
    assert [b.text for b in last_page.inline_keyboard[0]] == ["B8"]
    assert "B8" not in [b.text for row in last_page.inline_keyboard[1:] for b in row]

    # Out-of-range page clamps instead of returning an empty grid.
    clamped = inline_menu_keyboard(fake(3), page=99)
    assert len(clamped.inline_keyboard) >= 1

    print("✓ inline_menu_keyboard: empty/single-page/last-page/out-of-range all render correctly")


def check_reply_keyboard_admin_row_and_empty_state():
    fake = [SimpleNamespace(label="A"), SimpleNamespace(label="B")]
    kb = reply_menu_keyboard(fake, is_admin=True)
    assert kb.keyboard[-1][0].text == "🛠 Admin Panel", "admin row must always be last, outside the DB rows"

    assert reply_menu_keyboard([], is_admin=False) is None, "zero buttons, non-admin -> no reply_markup at all"
    assert reply_menu_keyboard([], is_admin=True) is not None, "admin always keeps a way back into the panel"

    print("✓ reply_menu_keyboard: admin row placement and empty-state handling are correct")


def check_dispatch_table_covers_every_action():
    from bot.handlers.user.start import _ACTION_DISPATCH

    missing = set(MenuButtonAction) - set(_ACTION_DISPATCH.keys())
    assert not missing, f"these actions have no dispatch entry and would KeyError on tap: {missing}"
    print("✓ every MenuButtonAction has a dispatch-table entry in start.py")


if __name__ == "__main__":
    asyncio.run(check_rename_survives_via_filter())
    asyncio.run(check_hidden_button_does_not_match())
    asyncio.run(check_crud_and_reorder())
    check_inline_pagination_edges()
    check_reply_keyboard_admin_row_and_empty_state()
    check_dispatch_table_covers_every_action()
    print("\nAll dynamic menu checks passed.")
