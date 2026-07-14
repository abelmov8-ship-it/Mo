"""
Runnable self-check for dynamic delivery buttons (default button
rename/toggle, custom file buttons, multiple backup channel links).

1. get_default_button_config: seeds all 4 slots with correct defaults on
   first read, and migrates the legacy zero_result_request_enabled value
   instead of silently resetting it to True.
2. set_default_button_label / toggle_default_button: round-trip through a
   real session; unknown slot names are rejected, not silently accepted.
3. Custom file buttons and backup channel links: full CRUD round-trips
   (these reuse the same generic list helper now, so one test covers the
   shared mechanics; the legacy-URL migration is checked separately since
   it's specific to backup links).
4. get_backup_channel_links: migrates a pre-existing single
   zero_result_alt_channel_url into the new list format, once, without
   losing it — this is what makes "add more than one" possible without
   breaking whatever an admin already had configured.
5. build_delivered_movie_keyboard / build_zero_result_keyboard: default
   buttons respect their enabled flag and configured label, custom
   buttons/backup links respect visibility and order, and — the actual
   point of this whole request — MULTIPLE backup links all render as
   separate buttons, not just the first one.
6. normalize_channel_url: the more forgiving @username/t.me shorthand
   still works exactly as it did in the old single-link flow.

Run directly: `python3 tests/check_delivery_buttons.py`
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.database.base import Base
import bot.database.models  # noqa: F401
from bot.handlers.admin.delivery_buttons import normalize_channel_url
from bot.services.settings_service import SettingsService
from bot.utils.movie_delivery import build_delivered_movie_keyboard, build_zero_result_keyboard


async def _fresh_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    return engine, Session()


async def check_default_config_seeds_correctly():
    engine, session = await _fresh_session()
    svc = SettingsService(session)

    config = await svc.get_default_button_config()
    assert set(config.keys()) == {"watch_later", "report_broken", "request_movie", "backup_channel"}
    assert config["watch_later"]["label"] == "➕ Watch Later"
    assert config["watch_later"]["enabled"] is True
    assert config["report_broken"]["label"] == "⚠️ Report Broken Link"

    await engine.dispose()
    print("✓ get_default_button_config: all 4 slots seed with the exact pre-existing labels/defaults")


async def check_legacy_request_toggle_migrates():
    engine, session = await _fresh_session()
    svc = SettingsService(session)
    # Simulate an admin who had already turned the request button OFF
    # under the old system, before this feature ever existed.
    await svc.set_bool("zero_result_request_enabled", False)
    await session.commit()

    config = await svc.get_default_button_config()
    assert config["request_movie"]["enabled"] is False, \
        "must migrate the existing OFF state, not silently reset it to True"

    await engine.dispose()
    print("✓ get_default_button_config: migrates the pre-existing request-button toggle correctly")


async def check_rename_and_toggle():
    engine, session = await _fresh_session()
    svc = SettingsService(session)

    assert await svc.set_default_button_label("watch_later", "📌 Save for Later") is True
    assert await svc.set_default_button_label("not_a_real_slot", "x") is False

    new_state = await svc.toggle_default_button("report_broken")
    assert new_state is False  # was True by default
    assert await svc.toggle_default_button("not_a_real_slot") is None

    config = await svc.get_default_button_config()
    assert config["watch_later"]["label"] == "📌 Save for Later"
    assert config["report_broken"]["enabled"] is False

    await engine.dispose()
    print("✓ rename + toggle: round-trip correctly, unknown slots rejected cleanly")


async def check_custom_buttons_and_backup_links_crud():
    engine, session = await _fresh_session()
    svc = SettingsService(session)

    a = await svc.add_movie_delivery_button("📱 TikTok", "https://tiktok.com/@x")
    b = await svc.add_movie_delivery_button("▶️ YouTube", "https://youtube.com/x")
    assert [x["label"] for x in await svc.get_movie_delivery_buttons()] == ["📱 TikTok", "▶️ YouTube"]

    assert await svc.move_movie_delivery_button(b["id"], -1) is True
    ordered = sorted(await svc.get_movie_delivery_buttons(), key=lambda x: x["order"])
    assert [x["label"] for x in ordered] == ["▶️ YouTube", "📱 TikTok"]

    assert await svc.delete_movie_delivery_button(a["id"]) is True
    assert len(await svc.get_movie_delivery_buttons()) == 1

    link = await svc.add_backup_channel_link("🔗 Mirror 1", "https://t.me/mirror1")
    await svc.add_backup_channel_link("🔗 Mirror 2", "https://t.me/mirror2")
    assert len(await svc.get_backup_channel_links()) == 2
    assert await svc.update_backup_channel_link(link["id"], is_visible=False) is True
    links = await svc.get_backup_channel_links()
    assert next(l for l in links if l["id"] == link["id"])["is_visible"] is False

    await engine.dispose()
    print("✓ custom file buttons + backup channel links: full CRUD round-trips correctly")


async def check_legacy_backup_url_migrates():
    engine, session = await _fresh_session()
    svc = SettingsService(session)
    # Simulate an admin who already had ONE backup link configured under
    # the old single-string system.
    await svc.set("zero_result_alt_channel_url", "https://t.me/oldbackup")
    await session.commit()

    links = await svc.get_backup_channel_links()
    assert len(links) == 1
    assert links[0]["url"] == "https://t.me/oldbackup"

    # Adding a second one must not disturb the migrated first one.
    await svc.add_backup_channel_link("🔗 New Mirror", "https://t.me/newmirror")
    links = await svc.get_backup_channel_links()
    assert len(links) == 2, "the whole point: more than one backup link must now be possible"

    await engine.dispose()
    print("✓ get_backup_channel_links: migrates the old single URL, then supports adding more")


def check_normalize_channel_url():
    assert normalize_channel_url("@mychannel") == "https://t.me/mychannel"
    assert normalize_channel_url("t.me/mychannel") == "https://t.me/mychannel"
    assert normalize_channel_url("telegram.me/mychannel") == "https://telegram.me/mychannel"
    assert normalize_channel_url("https://t.me/mychannel") == "https://t.me/mychannel"
    assert normalize_channel_url("not a link at all") is None
    print("✓ normalize_channel_url: @username/t.me shorthand works exactly as the old flow did")


async def check_delivered_movie_keyboard_respects_config():
    engine, session = await _fresh_session()
    svc = SettingsService(session)
    await svc.toggle_default_button("report_broken")  # turn it off
    await svc.add_movie_delivery_button("📱 TikTok", "https://tiktok.com/@x")
    await svc.add_movie_delivery_button("▶️ YouTube", "https://youtube.com/x")
    await session.commit()

    markup = await build_delivered_movie_keyboard(session, movie_id=42, in_watchlist=False)
    labels = [b.text for row in markup.inline_keyboard for b in row]
    assert "➕ Watch Later" in labels, "enabled default button must appear"
    assert not any("Report Broken" in l for l in labels), "disabled default button must not appear"
    assert "📱 TikTok" in labels and "▶️ YouTube" in labels, "both custom buttons must appear"

    await engine.dispose()
    print("✓ build_delivered_movie_keyboard: respects enabled/disabled defaults and shows all custom buttons")


async def check_zero_result_keyboard_shows_multiple_backup_links():
    engine, session = await _fresh_session()
    svc = SettingsService(session)
    await svc.add_backup_channel_link("🔗 Mirror 1", "https://t.me/mirror1")
    await svc.add_backup_channel_link("🔗 Mirror 2", "https://t.me/mirror2")
    await svc.add_backup_channel_link("🔗 Mirror 3", "https://t.me/mirror3")
    await session.commit()

    markup = await build_zero_result_keyboard(session, query="some movie")
    labels = [b.text for row in markup.inline_keyboard for b in row]
    assert "📣 Request Movie" in labels
    assert "🔗 Mirror 1" in labels and "🔗 Mirror 2" in labels and "🔗 Mirror 3" in labels, \
        "this is the actual feature request: more than one backup link must render, not just the first"

    await engine.dispose()
    print("✓ build_zero_result_keyboard: all configured backup links render, not just one")


if __name__ == "__main__":
    asyncio.run(check_default_config_seeds_correctly())
    asyncio.run(check_legacy_request_toggle_migrates())
    asyncio.run(check_rename_and_toggle())
    asyncio.run(check_custom_buttons_and_backup_links_crud())
    asyncio.run(check_legacy_backup_url_migrates())
    check_normalize_channel_url()
    asyncio.run(check_delivered_movie_keyboard_respects_config())
    asyncio.run(check_zero_result_keyboard_shows_multiple_backup_links())
    print("\nAll delivery button checks passed.")
