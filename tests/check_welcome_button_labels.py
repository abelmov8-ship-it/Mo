"""
Runnable self-check for bilingual welcome-message button labels
(SettingsService welcome_buttons + welcome_buttons_keyboard, using the
shared button_label() resolver in bot.services.settings_service — the same
one movie_delivery_buttons and backup_channel_links use, since all three
are the same generic (label, url) list shape).

Unlike MenuButton (an ORM table, needed a migration), welcome buttons are
plain dicts in a JSON blob (SettingsService.get/add/update_welcome_button),
so label_am is just an optional dict key — no schema change, and
SettingsService needed zero code changes: update_button_in_list() already
does a generic dict.update(**fields), so update_welcome_button(id,
label_am=...) worked the moment the rendering side knew to look for it.

Also unlike MenuButton, welcome buttons are Telegram URL buttons, not
callback_data ones — tapping one opens the link client-side with no
round-trip to the bot, so there's no tap-matching filter to worry about
breaking here (that was specifically a reply-keyboard problem).

Covers:
1. A button with no label_am renders its label in both languages.
2. A button with label_am renders label_am for Amharic, label for English.
3. update_welcome_button can set AND clear label_am via the existing
   generic kwargs path.
4. welcome_buttons_keyboard() end-to-end: the actual button text in the
   built keyboard matches the expected language, for both the paginated
   and non-paginated (nav-off) code paths.

Run directly: `python3 tests/check_welcome_button_labels.py`
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
from bot.keyboards.user.main_menu import welcome_buttons_keyboard
from bot.services.settings_service import SettingsService, button_label


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


def _button_texts(markup) -> list[str]:
    return [btn.text for row in markup.inline_keyboard for btn in row]


async def main() -> None:
    session = await _session()
    svc = SettingsService(session)

    # 1 & 3. Add English-only, confirm fallback, then add + clear an
    # Amharic label via the existing generic update path.
    btn = await svc.add_welcome_button("📱 Follow on TikTok", "https://tiktok.com/@example")
    check("no label_am: EN request shows the English label",
          button_label(btn, UserLanguage.EN) == "📱 Follow on TikTok")
    check("no label_am: AM request falls back to the English label",
          button_label(btn, UserLanguage.AM) == "📱 Follow on TikTok")

    await svc.update_welcome_button(btn["id"], label_am="📱 በቲክቶክ ይከተሉን")
    buttons = await svc.get_welcome_buttons()
    btn = next(b for b in buttons if b["id"] == btn["id"])
    check("label_am set: AM request now shows it",
          button_label(btn, UserLanguage.AM) == "📱 በቲክቶክ ይከተሉን")
    check("label_am set: EN request is unaffected",
          button_label(btn, UserLanguage.EN) == "📱 Follow on TikTok")
    check("button_label also accepts a plain 'am' string, not just UserLanguage.AM",
          button_label(btn, "am") == "📱 በቲክቶክ ይከተሉን")

    await svc.update_welcome_button(btn["id"], label_am=None)
    buttons = await svc.get_welcome_buttons()
    btn = next(b for b in buttons if b["id"] == btn["id"])
    check("clearing label_am reverts AM requests back to the English label",
          button_label(btn, UserLanguage.AM) == "📱 Follow on TikTok")

    # 2 & 4. End-to-end through welcome_buttons_keyboard, both code paths,
    # with two buttons: one bilingual, one English-only.
    await svc.update_welcome_button(btn["id"], label_am="📱 በቲክቶክ ይከተሉን")
    await svc.add_welcome_button("🐦 Follow on X", "https://x.com/example")
    buttons = await svc.get_welcome_buttons()

    en_texts = _button_texts(welcome_buttons_keyboard(buttons, paginated=False, locale=UserLanguage.EN))
    am_texts = _button_texts(welcome_buttons_keyboard(buttons, paginated=False, locale=UserLanguage.AM))
    check("non-paginated EN keyboard shows both English labels",
          en_texts == ["📱 Follow on TikTok", "🐦 Follow on X"])
    check("non-paginated AM keyboard shows Amharic where set, English fallback otherwise",
          am_texts == ["📱 በቲክቶክ ይከተሉን", "🐦 Follow on X"])

    am_texts_paginated = _button_texts(welcome_buttons_keyboard(buttons, page=0, paginated=True, locale=UserLanguage.AM))
    check("paginated code path resolves the same per-button language as non-paginated",
          am_texts_paginated == am_texts)

    await session.close()
    print("\nAll welcome-button bilingual-label checks passed.")


asyncio.run(main())
