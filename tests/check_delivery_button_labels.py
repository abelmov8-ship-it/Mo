"""
Runnable self-check for bilingual movie-delivery buttons and backup
channel links (SettingsService.update_movie_delivery_button /
update_backup_channel_link + utils.movie_delivery's two keyboard builders).

Third consumer of the same generic (label, url) list shape as welcome
buttons (see check_welcome_button_labels.py) — label_am is again just an
optional dict key, no schema change, and the shared button_label()
resolver in bot.services.settings_service is what both keyboard builders
now use. This file exercises the actual production functions
(build_delivered_movie_keyboard / build_zero_result_keyboard) rather than
re-proving button_label()'s fallback logic a third time, since that part
is already covered.

Also confirms the render-time URL-scheme guard (a button with a bad url
must not silently disappear or break the rest of the keyboard) still
applies with a label_am present, since that guard runs before the label
is even chosen.

Covers:
1. update_movie_delivery_button / update_backup_channel_link can set and
   clear label_am via the existing generic kwargs path (same mechanism,
   different callers than welcome buttons — worth confirming directly
   since this request is specifically about these two).
2. build_delivered_movie_keyboard shows the Amharic label for AM, English
   for EN, alongside the movie itself needing no changes.
3. build_zero_result_keyboard: same, for backup channel links.
4. A backup link with an invalid URL is still excluded from the keyboard
   even once it has a label_am set — the guard isn't only checked before
   bilingual support existed.

Run directly: `python3 tests/check_delivery_button_labels.py`
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
from bot.utils.movie_delivery import build_delivered_movie_keyboard, build_zero_result_keyboard


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

    # 1. Generic CRUD path, called the way the admin handlers actually call it.
    movie_btn = await svc.add_movie_delivery_button(label="🔔 Join Updates Channel", url="https://t.me/example")
    await svc.update_movie_delivery_button(movie_btn["id"], label_am="🔔 የዝማኔ ቻናል ይቀላቀሉ")
    buttons = await svc.get_movie_delivery_buttons()
    movie_btn = next(b for b in buttons if b["id"] == movie_btn["id"])
    check("movie delivery button: label_am set via update_movie_delivery_button",
          movie_btn["label_am"] == "🔔 የዝማኔ ቻናል ይቀላቀሉ")

    await svc.update_movie_delivery_button(movie_btn["id"], label_am=None)
    buttons = await svc.get_movie_delivery_buttons()
    movie_btn = next(b for b in buttons if b["id"] == movie_btn["id"])
    check("movie delivery button: label_am cleared via update_movie_delivery_button",
          not movie_btn.get("label_am"))

    backup_link = await svc.add_backup_channel_link(label="🔗 Backup Channel 2", url="https://t.me/backup2")
    await svc.update_backup_channel_link(backup_link["id"], label_am="🔗 መጠባበቂያ ቻናል 2")
    links = await svc.get_backup_channel_links()
    backup_link = next(l for l in links if l["id"] == backup_link["id"])
    check("backup channel link: label_am set via update_backup_channel_link",
          backup_link["label_am"] == "🔗 መጠባበቂያ ቻናል 2")

    # 2. build_delivered_movie_keyboard end-to-end, both languages.
    await svc.update_movie_delivery_button(movie_btn["id"], label_am="🔔 የዝማኔ ቻናል ይቀላቀሉ")
    en_markup = await build_delivered_movie_keyboard(session, movie_id=1, locale=UserLanguage.EN)
    am_markup = await build_delivered_movie_keyboard(session, movie_id=1, locale=UserLanguage.AM)
    check("delivered-movie keyboard (EN): shows the English custom-button label",
          "🔔 Join Updates Channel" in _button_texts(en_markup))
    check("delivered-movie keyboard (AM): shows the Amharic custom-button label",
          "🔔 የዝማኔ ቻናል ይቀላቀሉ" in _button_texts(am_markup))
    check("delivered-movie keyboard (AM): does NOT show the raw English label instead",
          "🔔 Join Updates Channel" not in _button_texts(am_markup))

    # 3. build_zero_result_keyboard end-to-end, both languages.
    en_markup = await build_zero_result_keyboard(session, query="some movie", locale=UserLanguage.EN)
    am_markup = await build_zero_result_keyboard(session, query="some movie", locale=UserLanguage.AM)
    check("zero-result keyboard (EN): shows the English backup-link label",
          "🔗 Backup Channel 2" in _button_texts(en_markup))
    check("zero-result keyboard (AM): shows the Amharic backup-link label",
          "🔗 መጠባበቂያ ቻናል 2" in _button_texts(am_markup))

    # 4. The render-time invalid-URL guard still excludes a link, label_am or not.
    bad_link = await svc.add_backup_channel_link(label="🚫 Bad Link", url="not-a-valid-url")
    await svc.update_backup_channel_link(bad_link["id"], label_am="🚫 መጥፎ አገናኝ")
    am_markup = await build_zero_result_keyboard(session, query="some movie", locale=UserLanguage.AM)
    check("a backup link with an invalid URL is excluded even with label_am set",
          "🚫 መጥፎ አገናኝ" not in _button_texts(am_markup) and "🚫 Bad Link" not in _button_texts(am_markup))

    await session.close()
    print("\nAll movie-delivery/backup-link bilingual-label checks passed.")


asyncio.run(main())
