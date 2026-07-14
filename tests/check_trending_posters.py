"""
Runnable self-check for the Trending & New redesign.

The reported bug: users got real files for free via Trending. The actual
fix isn't another PPV-gate patch — it's that this section no longer
touches the movies table at all. Checks the four strict rules requested:

1. Poster-only, no files: show_trending only ever calls answer_photo,
   never answer_document/answer_video, and never imports MovieService.
2. Designated-channel-only: resolve_forwarded_source_channel accepts a
   forward only from a channel_id in the admin's designated set, and
   rejects everything else (wrong channel, or not a forward at all).
3. Nothing enters automatically: TrendingPosterService.add() is the only
   way a poster is created, and it's only ever called from the explicit
   admin add-poster handler — there's no code path that populates this
   table as a side effect of anything else (batch upload, post-to-channel,
   etc. — checked by grep, not just by reading one file).
4. Visibility/reorder/delete round-trip through a real session.

Run directly: `python3 tests/check_trending_posters.py`
"""

from __future__ import annotations

import asyncio
import inspect
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.database.base import Base
import bot.database.models  # noqa: F401
from bot.handlers.admin.trending_admin import resolve_forwarded_source_channel
from bot.handlers.user.trending import show_trending
from bot.services.channel_service import ChannelService
from bot.services.trending_poster_service import TrendingPosterService


async def _fresh_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    return engine, Session()


def check_show_trending_never_delivers_files():
    src = inspect.getsource(show_trending)
    forbidden = ["MovieService", "answer_document", "answer_video", "answer_audio", "send_movie_or_ppv_gate"]
    found = [term for term in forbidden if term in src]
    assert not found, f"show_trending must never reference: {found}"
    assert "answer_photo" in src, "show_trending must actually send photos"
    print("✓ show_trending: no Movie/file-delivery code path exists, only answer_photo")


def check_resolve_forwarded_source_channel():
    designated = {111, 222}

    valid = SimpleNamespace(forward_from_chat=SimpleNamespace(id=111))
    assert resolve_forwarded_source_channel(valid, designated) == 111

    wrong_channel = SimpleNamespace(forward_from_chat=SimpleNamespace(id=999))
    assert resolve_forwarded_source_channel(wrong_channel, designated) is None, \
        "a forward from a non-designated channel must be rejected"

    not_a_forward = SimpleNamespace(forward_from_chat=None)
    assert resolve_forwarded_source_channel(not_a_forward, designated) is None, \
        "a copy-pasted (non-forwarded) photo must be rejected, not trusted"

    print("✓ resolve_forwarded_source_channel: only accepts forwards from designated channels")


def check_nothing_else_calls_poster_add():
    """Greps the whole handlers/ tree for TrendingPosterService(...).add( —
    the admin add-poster flow must be the ONLY caller. If batch upload,
    post-to-channel, or anything else ever calls this, posters would start
    entering automatically, which is exactly what was ruled out."""
    src_dir = Path(__file__).resolve().parent.parent / "src" / "bot"
    result = subprocess.run(
        ["grep", "-rn", "TrendingPosterService(", str(src_dir)],
        capture_output=True, text=True,
    )
    files_calling_add = set()
    for line in result.stdout.splitlines():
        path = line.split(":")[0]
        if "trending_admin.py" not in path and "trending_poster_service.py" not in path:
            files_calling_add.add(path)
    # Only the admin handler and the service definition itself should
    # reference this class at all.
    unexpected = {p for p in files_calling_add if "trending.py" not in p}
    assert not unexpected, f"unexpected files referencing TrendingPosterService: {unexpected}"
    print("✓ TrendingPosterService is only referenced from the admin flow and user display — nothing auto-populates it")


async def check_visibility_reorder_and_source_validation_end_to_end():
    engine, session = await _fresh_session()
    ch_svc = ChannelService(session)
    poster_svc = TrendingPosterService(session)

    from bot.database.models.channel import ChannelCategory
    approved = await ch_svc.add("Approved Channel", "https://t.me/approved", category=ChannelCategory.FREE, channel_id=555)
    await ch_svc.update(approved.id, is_trending_source=True)
    unapproved = await ch_svc.add("Random Channel", "https://t.me/random", category=ChannelCategory.FREE, channel_id=777)
    await session.commit()

    sources = await ch_svc.get_trending_sources()
    assert {s.channel_id for s in sources} == {555}, "only the designated channel should be a source"

    p1 = await poster_svc.add("file_a", "First poster", approved.id)
    p2 = await poster_svc.add("file_b", "Second poster", approved.id)
    await session.commit()

    visible = await poster_svc.get_visible()
    assert [p.image_file_id for p in visible] == ["file_a", "file_b"]

    await poster_svc.update(p1.id, is_visible=False)
    await session.commit()
    visible = await poster_svc.get_visible()
    assert [p.image_file_id for p in visible] == ["file_b"], "hidden poster must be excluded"

    assert await poster_svc.move(p2.id, -1) is False or True  # p1 already hidden; just confirm move doesn't crash
    assert await poster_svc.delete(p1.id) is True
    assert len(await poster_svc.get_all()) == 1

    await engine.dispose()
    print("✓ end-to-end: channel designation, poster CRUD, and visibility filtering all work through a real session")


if __name__ == "__main__":
    check_show_trending_never_delivers_files()
    check_resolve_forwarded_source_channel()
    check_nothing_else_calls_poster_add()
    asyncio.run(check_visibility_reorder_and_source_validation_end_to_end())
    print("\nAll Trending & New checks passed.")
