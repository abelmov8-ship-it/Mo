"""
Runnable self-check for Phase 4 (welcome message buttons + dynamic nav).

1. SettingsService welcome-button CRUD: add/update/delete/move round-trip
   through a real session, using the same JSON-in-Settings pattern as the
   existing bank_accounts feature (no new table for this phase).
2. validate_button_url: the trust-boundary check on admin-entered URLs
   before they become a live Telegram button.
3. welcome_buttons_keyboard: empty state, pagination page boundaries, the
   paginated=False "show everything" mode, and that hidden buttons are
   filtered while order is respected — mirrors the same last-page/leftover
   edge case caught in Phase 3's inline_menu_keyboard, since this reuses
   that exact technique.
4. The nav-enabled toggle actually round-trips through get_bool/set_bool.

Run directly: `python3 tests/check_welcome_buttons.py`
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.database.base import Base
import bot.database.models  # noqa: F401  registers all models on Base.metadata
from bot.handlers.admin.welcome_buttons import validate_button_url
from bot.keyboards.user.main_menu import welcome_buttons_keyboard
from bot.services.settings_service import SettingsService


async def _fresh_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    return engine, Session()


def check_url_validation():
    assert validate_button_url("https://tiktok.com/@x") == "https://tiktok.com/@x"
    assert validate_button_url("http://example.com") == "http://example.com"
    assert validate_button_url("tg://resolve?domain=x") == "tg://resolve?domain=x"
    assert validate_button_url("  https://x.com  ") == "https://x.com", "must trim whitespace"

    assert validate_button_url("tiktok.com/@x") is None, "missing scheme must be rejected"
    assert validate_button_url("javascript:alert(1)") is None
    assert validate_button_url("https://" + "a" * 600) is None, "oversized URL must be rejected"
    print("✓ validate_button_url: accepts real schemes, rejects missing/oversized/unsafe input")


async def check_settings_service_crud_and_reorder():
    engine, session = await _fresh_session()
    svc = SettingsService(session)

    a = await svc.add_welcome_button("A", "https://a.com")
    b = await svc.add_welcome_button("B", "https://b.com")
    c = await svc.add_welcome_button("C", "https://c.com")
    await session.commit()

    ordered = sorted(await svc.get_welcome_buttons(), key=lambda x: x["order"])
    assert [x["label"] for x in ordered] == ["A", "B", "C"]

    assert await svc.move_welcome_button(c["id"], -1) is True
    await session.commit()
    ordered = sorted(await svc.get_welcome_buttons(), key=lambda x: x["order"])
    assert [x["label"] for x in ordered] == ["A", "C", "B"], f"got {[x['label'] for x in ordered]}"

    assert await svc.move_welcome_button(a["id"], -1) is False, "moving the first item up must be a no-op"

    assert await svc.update_welcome_button(b["id"], label="B-renamed", url="https://b2.com") is True
    updated = next(x for x in await svc.get_welcome_buttons() if x["id"] == b["id"])
    assert updated["label"] == "B-renamed" and updated["url"] == "https://b2.com"

    assert await svc.delete_welcome_button(a["id"]) is True
    assert await svc.delete_welcome_button(9999) is False
    assert len(await svc.get_welcome_buttons()) == 2

    await engine.dispose()
    print("✓ SettingsService welcome-button CRUD + reorder round-trip correctly")


async def check_nav_toggle_roundtrip():
    engine, session = await _fresh_session()
    svc = SettingsService(session)

    assert await svc.get_bool("welcome_nav_enabled", default=True) is True, "default before any admin action"
    await svc.set_bool("welcome_nav_enabled", False)
    await session.commit()
    assert await svc.get_bool("welcome_nav_enabled", default=True) is False

    await engine.dispose()
    print("✓ welcome_nav_enabled toggle round-trips through Settings")


def check_pagination_and_visibility():
    def fake(n):
        return [{"id": i, "label": f"B{i}", "url": f"https://x.com/{i}", "is_visible": True, "order": i}
                for i in range(n)]

    assert welcome_buttons_keyboard([]) is None

    # Last-page-with-one-leftover must not merge into the nav row — the
    # exact bug caught and fixed in Phase 3's inline_menu_keyboard, which
    # this reuses the same technique from.
    markup = welcome_buttons_keyboard(fake(9), page=2)  # page size 4 -> page 2 has 1 leftover
    assert [b.text for b in markup.inline_keyboard[0]] == ["B8"]
    assert "B8" not in [b.text for row in markup.inline_keyboard[1:] for b in row]

    # paginated=False must show every visible button, not just page 1.
    flat = welcome_buttons_keyboard(fake(9), paginated=False)
    all_texts = [b.text for row in flat.inline_keyboard for b in row]
    assert all_texts == [f"B{i}" for i in range(9)], "nav-off must not hide buttons past page 1"

    # Hidden buttons excluded, order respected regardless of insertion order.
    mixed = [
        {"id": 1, "label": "Hidden", "url": "https://x.com/1", "is_visible": False, "order": 0},
        {"id": 2, "label": "Second", "url": "https://x.com/2", "is_visible": True, "order": 2},
        {"id": 3, "label": "First",  "url": "https://x.com/3", "is_visible": True, "order": 1},
    ]
    rendered = [b.text for row in welcome_buttons_keyboard(mixed).inline_keyboard for b in row]
    assert rendered == ["First", "Second"], f"got {rendered}"

    print("✓ welcome_buttons_keyboard: pagination edges, nav-off mode, and visibility/order all correct")


if __name__ == "__main__":
    check_url_validation()
    asyncio.run(check_settings_service_crud_and_reorder())
    asyncio.run(check_nav_toggle_roundtrip())
    check_pagination_and_visibility()
    print("\nAll welcome button checks passed.")
