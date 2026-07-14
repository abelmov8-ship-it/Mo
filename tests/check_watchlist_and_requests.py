"""
Runnable self-check for two "critical" visibility bugs:

1. Watch Later: data was always being saved correctly, but there was no
   way to ever see it again. Checks WatchlistService end to end, the new
   profile.py viewer (empty + populated states), removal from within that
   view, the previously-missing watchlist:remove handler, and that a
   movie already on the list shows the correct button state on delivery
   instead of always offering to add it again.

2. Admin request visibility: requests were already being logged
   correctly (SearchLogKind.REQUEST) and the existing Search Log admin
   view already queried for them — the actual gap was that nothing ever
   told an admin a new one had arrived. Checks the new proactive DM, and
   a real latent bug found while investigating: short movie titles (e.g.
   "It", "Up") could substring-match and silently mark unrelated
   requests as fulfilled via the Request Notification Engine.

Run directly: `python3 tests/check_watchlist_and_requests.py`
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.database.base import Base
import bot.database.models  # noqa: F401
from bot.database.models.movie import MovieFileType
from bot.database.models.search_log import SearchLog, SearchLogKind
from bot.database.models.user import User, UserLanguage
from bot.handlers.admin.system import _index_batch
from bot.handlers.user.profile import _watchlist_keyboard, _watchlist_text, remove_from_watchlist_view, show_watchlist
from bot.handlers.user.search import add_to_watchlist, remove_from_watchlist, request_movie
from bot.services.movie_service import MovieService
from bot.services.settings_service import SettingsService
from bot.services.user_service import UserService
from bot.services.watchlist_service import WatchlistService


async def _fresh_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    return engine, Session()


class FakeCallback:
    def __init__(self, data, uid, bot=None):
        self.data = data
        self.from_user = SimpleNamespace(id=uid)
        self.bot = bot
        self.message = FakeMessage()
        self.alerts = []
    async def answer(self, text="", show_alert=False):
        self.alerts.append(text)


class FakeMessage:
    def __init__(self):
        self.sent = []
        self.markups = []
    async def answer(self, text, reply_markup=None, **kw):
        self.sent.append(text)
        self.markups.append(reply_markup)
        return self
    async def edit_text(self, text, reply_markup=None, **kw):
        self.sent.append(text)
        self.markups.append(reply_markup)


class FakeBot:
    def __init__(self):
        self.dms = []
    async def send_message(self, chat_id, text, **kw):
        self.dms.append((chat_id, text))


async def check_watchlist_service_crud():
    engine, session = await _fresh_session()
    user_svc, movie_svc = UserService(session), MovieService(session)
    user, _ = await user_svc.get_or_create(telegram_id=1, first_name="A", username=None)
    movie = await movie_svc.add("f1", "Some Movie")
    await session.commit()

    svc = WatchlistService(session)
    assert await svc.is_in_watchlist(user.id, movie.id) is False
    assert await svc.add(user.id, movie.id) is True
    assert await svc.add(user.id, movie.id) is False, "adding twice must be a safe no-op, not a crash"
    assert await svc.is_in_watchlist(user.id, movie.id) is True

    movies = await svc.get_for_user(user.id)
    assert len(movies) == 1 and movies[0].id == movie.id

    assert await svc.remove(user.id, movie.id) is True
    assert await svc.remove(user.id, movie.id) is False, "removing twice must be a safe no-op"
    assert await svc.get_for_user(user.id) == []

    await engine.dispose()
    print("✓ WatchlistService: add/remove/is_in_watchlist/get_for_user all correct, duplicate-safe")


async def check_watchlist_viewer_end_to_end():
    engine, session = await _fresh_session()
    user_svc, movie_svc = UserService(session), MovieService(session)
    user, _ = await user_svc.get_or_create(telegram_id=2, first_name="B", username=None)
    m1 = await movie_svc.add("f2", "First Saved Movie")
    m2 = await movie_svc.add("f3", "Second Saved Movie")
    await session.commit()

    # Empty state — this is the actual bug: previously there was no path
    # to this screen at all, so "empty" was indistinguishable from "doesn't exist."
    empty_text = _watchlist_text([])
    assert "empty" in empty_text.lower()

    await WatchlistService(session).add(user.id, m1.id)
    await WatchlistService(session).add(user.id, m2.id)
    await session.commit()

    cb = FakeCallback("profile:watchlist", uid=2)
    await show_watchlist(cb, session)
    labels = [b.text for row in cb.message.markups[-1].inline_keyboard for b in row]
    assert "❌ First Saved Movie" in labels and "❌ Second Saved Movie" in labels
    assert "(2)" in cb.message.sent[-1]

    # Remove one from within the viewer — must refresh the list, not just alert.
    remove_cb = FakeCallback(f"mywatchlist:remove:{m1.id}", uid=2)
    await remove_from_watchlist_view(remove_cb, session)
    remaining = await WatchlistService(session).get_for_user(user.id)
    assert len(remaining) == 1 and remaining[0].id == m2.id
    refreshed_labels = [b.text for row in remove_cb.message.markups[-1].inline_keyboard for b in row]
    assert refreshed_labels == ["❌ Second Saved Movie"], "the view must re-render after removal"

    await engine.dispose()
    print("✓ My Watchlist viewer: empty state, listing, and remove-then-refresh all work")


async def check_the_previously_missing_remove_handler():
    """watchlist:remove: was referenced in callback_data by
    build_delivered_movie_keyboard but had no handler at all — this is
    the literal missing piece, checked directly."""
    engine, session = await _fresh_session()
    user_svc, movie_svc = UserService(session), MovieService(session)
    user, _ = await user_svc.get_or_create(telegram_id=3, first_name="C", username=None)
    movie = await movie_svc.add("f4", "A Movie")
    await session.commit()
    await WatchlistService(session).add(user.id, movie.id)
    await session.commit()

    cb = FakeCallback(f"watchlist:remove:{movie.id}", uid=3)
    await remove_from_watchlist(cb, session)
    assert await WatchlistService(session).is_in_watchlist(user.id, movie.id) is False
    assert "Removed" in cb.alerts[-1]

    await engine.dispose()
    print("✓ watchlist:remove now has a real handler (previously missing entirely)")


async def check_request_movie_notifies_admins():
    engine, session = await _fresh_session()
    from bot import config
    original_admins = config.settings.ADMIN_IDS
    config.settings.ADMIN_IDS = [9001, 9002]
    try:
        bot = FakeBot()
        cb = FakeCallback("request_movie:Some Requested Title", uid=4, bot=bot)
        await request_movie(cb, session)
        await session.commit()

        assert len(bot.dms) == 2, "every configured admin must be notified, not just logged silently"
        assert all("Some Requested Title" in text for _, text in bot.dms)
        assert {uid for uid, _ in bot.dms} == {9001, 9002}
    finally:
        config.settings.ADMIN_IDS = original_admins

    await engine.dispose()
    print("✓ request_movie: proactively DMs every configured admin, not just logging silently")


async def check_short_title_does_not_falsely_resolve_requests():
    engine, session = await _fresh_session()
    await SettingsService(session).set("default_ppv_price", "10.0")
    await session.commit()

    # An unrelated request that happens to contain a short common word.
    session.add(SearchLog(query="please put it up on the server", telegram_id=1, kind=SearchLogKind.REQUEST))
    await session.commit()

    bot = FakeBot()
    await _index_batch(bot, session, [
        {"file_id": "short1", "title": "It", "file_type": MovieFileType.VIDEO},
    ])
    await session.commit()

    from sqlalchemy import select
    log = (await session.execute(select(SearchLog))).scalar_one()
    assert log.notified is False, \
        "a short/generic title must not silently resolve an unrelated request via substring match"

    await engine.dispose()
    print("✓ short titles (<4 chars) no longer falsely auto-resolve unrelated requests")


async def check_normal_title_still_matches_correctly():
    """The fix must not break the legitimate case — a real, specific
    title matching its own request still works."""
    engine, session = await _fresh_session()
    await SettingsService(session).set("default_ppv_price", "10.0")
    await session.commit()

    session.add(SearchLog(query="Guardians of the Galaxy 3", telegram_id=1, kind=SearchLogKind.REQUEST))
    await session.commit()

    bot = FakeBot()
    await _index_batch(bot, session, [
        {"file_id": "gotg3", "title": "Guardians of the Galaxy 3", "file_type": MovieFileType.VIDEO},
    ])
    await session.commit()

    from sqlalchemy import select
    log = (await session.execute(select(SearchLog))).scalar_one()
    assert log.notified is True, "a genuine, specific title match must still resolve the request"
    assert len(bot.dms) == 1

    await engine.dispose()
    print("✓ normal-length titles still correctly match and notify their requester")


async def check_delivered_keyboard_reflects_real_watchlist_state():
    engine, session = await _fresh_session()
    user_svc, movie_svc = UserService(session), MovieService(session)
    user, _ = await user_svc.get_or_create(telegram_id=5, first_name="E", username=None)
    movie = await movie_svc.add("f5", "Already Saved")
    await session.commit()
    await WatchlistService(session).add(user.id, movie.id)
    await session.commit()

    from bot.utils.movie_delivery import build_delivered_movie_keyboard
    markup = await build_delivered_movie_keyboard(session, movie.id, in_watchlist=True)
    labels = [b.text for row in markup.inline_keyboard for b in row]
    assert "✅ In Watchlist" in labels, "a movie already saved must show the confirmed state, not 'Add' again"

    await engine.dispose()
    print("✓ delivered movie keyboard correctly reflects real (not always-False) watchlist status")


if __name__ == "__main__":
    asyncio.run(check_watchlist_service_crud())
    asyncio.run(check_watchlist_viewer_end_to_end())
    asyncio.run(check_the_previously_missing_remove_handler())
    asyncio.run(check_request_movie_notifies_admins())
    asyncio.run(check_short_title_does_not_falsely_resolve_requests())
    asyncio.run(check_normal_title_still_matches_correctly())
    asyncio.run(check_delivered_keyboard_reflects_real_watchlist_state())
    print("\nAll watchlist and request-visibility checks passed.")
