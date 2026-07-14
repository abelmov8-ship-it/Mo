"""
Runnable self-check for bilingual default-button-slot labels (Watch Later /
Report Broken Link / Request Movie / Check Backup Channel) —
SettingsService.set_default_button_label / clear_default_button_label_am +
utils.movie_delivery's two keyboard builders.

Fourth and last consumer of button_label() in this series, but a
structurally different one: watch_later/report_broken/request_movie/
backup_channel are four fixed, always-present dict slots (config[slot] =
{"label", "label_am", "enabled"}), not an admin-addable list — no id, no
url, no is_visible/order to sort by. button_label() still applies
directly, since it only ever looks at "label"/"label_am" on whatever dict
it's handed.

Also specifically covers a bug this session caught while wiring this up:
the Watch Later button has two visible states — "add" (renders
watch_later's admin-editable label) and "already added" (previously the
hardcoded string "✅ In Watchlist", now bot.utils.i18n key
movie.in_watchlist_label). Only fixing the "add" state would have meant
the button visibly flips from Amharic to English text the moment a user
taps it once.

Known gap this does NOT close: backup_channel["label"] (and now
label_am) accepts input and saves correctly, but nothing in
build_zero_result_keyboard actually renders it — the visible backup-link
buttons each carry their own label from get_backup_channel_links()
instead (see check_delivery_button_labels.py). Pre-existing, not
something bilingual support could fix on its own; check 5 below records
this rather than papering over it.

Run directly: `python3 tests/check_default_button_labels.py`
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
from bot.utils.i18n import save_text_override
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

    # 1. set/clear via the service, on two different slots.
    await svc.set_default_button_label("watch_later", "am", "➕ በኋላ ይመልከቱ")
    await svc.set_default_button_label("report_broken", "am", "⚠️ የተበላሸ አገናኝ ሪፖርት ያድርጉ")
    config = await svc.get_default_button_config()
    check("watch_later: label_am set via set_default_button_label",
          config["watch_later"]["label_am"] == "➕ በኋላ ይመልከቱ")
    check("report_broken: label_am set independently of watch_later",
          config["report_broken"]["label_am"] == "⚠️ የተበላሸ አገናኝ ሪፖርት ያድርጉ")
    check("request_movie: untouched slot has no label_am",
          not config["request_movie"].get("label_am"))

    await svc.clear_default_button_label_am("report_broken")
    config = await svc.get_default_button_config()
    check("report_broken: label_am cleared, watch_later's is unaffected",
          not config["report_broken"].get("label_am") and config["watch_later"]["label_am"] == "➕ በኋላ ይመልከቱ")
    await svc.set_default_button_label("report_broken", "am", "⚠️ የተበላሸ አገናኝ ሪፖርት ያድርጉ")  # restore for below

    # 2. build_delivered_movie_keyboard: the "add to watchlist" state.
    en_markup = await build_delivered_movie_keyboard(session, movie_id=1, in_watchlist=False, locale=UserLanguage.EN)
    am_markup = await build_delivered_movie_keyboard(session, movie_id=1, in_watchlist=False, locale=UserLanguage.AM)
    check("delivered-movie keyboard (EN): default Watch Later label",
          "➕ Watch Later" in _button_texts(en_markup))
    check("delivered-movie keyboard (AM): Amharic Watch Later label",
          "➕ በኋላ ይመልከቱ" in _button_texts(am_markup))
    check("delivered-movie keyboard (AM): Report Broken Link is also Amharic",
          "⚠️ የተበላሸ አገናኝ ሪፖርት ያድርጉ" in _button_texts(am_markup))

    # 3. The toggled ("already added") state — the bug this test exists to
    # pin down. movie.in_watchlist_label ships English-only (no invented
    # Amharic translation — same policy as every other new key from this
    # session), so to actually prove the AM path is live rather than just
    # falling back to English either way, set a real override for it here.
    await save_text_override(session, "movie.in_watchlist_label", "am", "✅ በዝርዝር ውስጥ")

    en_toggled = await build_delivered_movie_keyboard(session, movie_id=1, in_watchlist=True, locale=UserLanguage.EN)
    am_toggled = await build_delivered_movie_keyboard(session, movie_id=1, in_watchlist=True, locale=UserLanguage.AM)
    check("toggled state (EN): shows the in-watchlist label via t(), not the untoggled admin label",
          "✅ In Watchlist" in _button_texts(en_toggled) and "➕ Watch Later" not in _button_texts(en_toggled))
    check("toggled state (AM): with an override set, shows Amharic — proves this is live through t(), "
          "not a hardcoded string that can only ever say 'In Watchlist'",
          "✅ በዝርዝር ውስጥ" in _button_texts(am_toggled) and "✅ In Watchlist" not in _button_texts(am_toggled))

    # 4. build_zero_result_keyboard: request_movie slot.
    await svc.set_default_button_label("request_movie", "am", "📣 ፊልም ይጠይቁ")
    en_markup = await build_zero_result_keyboard(session, query="test", locale=UserLanguage.EN)
    am_markup = await build_zero_result_keyboard(session, query="test", locale=UserLanguage.AM)
    check("zero-result keyboard (EN): default Request Movie label",
          "📣 Request Movie" in _button_texts(en_markup))
    check("zero-result keyboard (AM): Amharic Request Movie label",
          "📣 ፊልም ይጠይቁ" in _button_texts(am_markup))

    # 5. Known gap, recorded rather than hidden: backup_channel's own
    # label_am saves correctly but isn't rendered by anything today (the
    # visible backup-link buttons come from get_backup_channel_links()
    # instead — see check_delivery_button_labels.py). This check exists so
    # that if someone later wires backup_channel["label"] into a render
    # path, they'll find this assertion and know to extend it, rather than
    # this gap being silently forgotten.
    await svc.set_default_button_label("backup_channel", "am", "🔗 መጠባበቂያ ቻናል ያረጋግጡ")
    config = await svc.get_default_button_config()
    am_markup = await build_zero_result_keyboard(session, query="test", locale=UserLanguage.AM)
    check("backup_channel: label_am saves correctly at the data layer",
          config["backup_channel"]["label_am"] == "🔗 መጠባበቂያ ቻናል ያረጋግጡ")
    check("backup_channel: ...but is confirmed NOT rendered anywhere yet (pre-existing, not this feature's gap)",
          "🔗 መጠባበቂያ ቻናል ያረጋግጡ" not in _button_texts(am_markup))

    await session.close()
    print("\nAll default-button-slot bilingual-label checks passed.")


asyncio.run(main())
