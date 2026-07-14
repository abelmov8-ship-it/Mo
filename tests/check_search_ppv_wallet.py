"""
Runnable self-check for the Search / PPV / Wallet fixes.

1. _resolve_media (admin/system.py): both ingestion call sites
   (batch upload, relink) shared this, and both silently dropped audio
   uploads. Checks all three media kinds resolve to the right file_type.
2. MovieService.batch_add: file_type actually persists through a real
   async session round-trip, not just accepted and dropped.
3. ppv_unlock_keyboard: the actual bug — VIP-upgrade used to be mutually
   exclusive with the wallet path. Checks both options are always present
   together, in every wallet-balance state.
4. deliver_movie: dispatches to the Telegram method matching file_type
   (audio/video/document) instead of always answer_document.
5. send_movie_or_ppv_gate: the trending.py bug — a PPV movie must show the
   unlock gate, never the raw file, regardless of which screen it's
   reached from. A free/VIP-eligible movie must deliver normally.

Run directly: `python3 tests/check_search_ppv_wallet.py`
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
from bot.database.models.movie import MovieFileType
from bot.database.models.user import User, UserLanguage
from bot.handlers.admin.system import _resolve_media
from bot.keyboards.user.payment import ppv_unlock_keyboard
from bot.services.movie_service import MovieService
from bot.utils.movie_delivery import deliver_movie, send_movie_or_ppv_gate


def _fake_message(video=None, audio=None, document=None):
    return SimpleNamespace(video=video, audio=audio, document=document)


def check_resolve_media():
    video = SimpleNamespace(file_id="v1")
    audio = SimpleNamespace(file_id="a1")
    document = SimpleNamespace(file_id="d1")

    media, ftype = _resolve_media(_fake_message(video=video))
    assert (media, ftype) == (video, MovieFileType.VIDEO)

    media, ftype = _resolve_media(_fake_message(audio=audio))
    assert (media, ftype) == (audio, MovieFileType.AUDIO), "audio must resolve, not fall through"

    media, ftype = _resolve_media(_fake_message(document=document))
    assert (media, ftype) == (document, MovieFileType.DOCUMENT)
    print("✓ _resolve_media: video, audio, and document all resolve correctly")


def check_ppv_unlock_keyboard():
    def labels(markup):
        return {btn.text for row in markup.inline_keyboard for btn in row}

    affordable = labels(ppv_unlock_keyboard(1, 50.0, wallet_ok=True))
    assert any("Unlock" in t for t in affordable)
    assert any("Upgrade to VIP" in t for t in affordable), "VIP upgrade must show even when wallet can pay"

    broke_topup_on = labels(ppv_unlock_keyboard(1, 50.0, wallet_ok=False))
    assert any("Top-up" in t for t in broke_topup_on)
    assert any("Upgrade to VIP" in t for t in broke_topup_on), "VIP upgrade must show alongside top-up"

    print("✓ ppv_unlock_keyboard: VIP-upgrade and the wallet path are always offered together")


class _RecordingMessage:
    """Duck-typed stand-in for aiogram.types.Message — records which
    answer_* method got called instead of hitting the Telegram API."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    async def _record(self, method, **kwargs):
        self.calls.append((method, kwargs))
        return SimpleNamespace(chat=SimpleNamespace(id=1), message_id=1)

    async def answer(self, text, **kwargs):
        return await self._record("answer", text=text, **kwargs)

    async def answer_video(self, video, **kwargs):
        return await self._record("answer_video", video=video, **kwargs)

    async def answer_audio(self, audio, **kwargs):
        return await self._record("answer_audio", audio=audio, **kwargs)

    async def answer_document(self, document, **kwargs):
        return await self._record("answer_document", document=document, **kwargs)


def _movie(**overrides):
    defaults = dict(id=1, title="T", file_id="f1", ppv_price=0.0, file_type=MovieFileType.VIDEO)
    defaults.update(overrides)
    return SimpleNamespace(is_ppv=defaults["ppv_price"] > 0, **defaults)


async def check_deliver_movie_dispatch():
    for ftype, expected_method in (
        (MovieFileType.VIDEO, "answer_video"),
        (MovieFileType.AUDIO, "answer_audio"),
        (MovieFileType.DOCUMENT, "answer_document"),
    ):
        msg = _RecordingMessage()
        await deliver_movie(msg, _movie(file_type=ftype))
        assert msg.calls[0][0] == expected_method, f"{ftype} should dispatch to {expected_method}"
    print("✓ deliver_movie: dispatches to the Telegram method matching file_type")


async def check_ppv_gate():
    free_movie = _movie(ppv_price=0.0)
    ppv_movie = _movie(ppv_price=100.0)
    free_user = User(telegram_id=1, first_name="A", language=UserLanguage.EN, is_vip=False, wallet_balance=0)
    vip_user = User(telegram_id=2, first_name="B", language=UserLanguage.EN, is_vip=True, wallet_balance=0)

    # Free movie: always delivered, regardless of who's asking.
    msg = _RecordingMessage()
    await send_movie_or_ppv_gate(msg, free_movie, free_user)
    assert msg.calls[0][0].startswith("answer_"), "free movie must deliver, not gate"

    # PPV movie, non-VIP, no wallet balance: must NOT deliver the file.
    # This is exactly the bug trending.py had — it always delivered.
    msg = _RecordingMessage()
    await send_movie_or_ppv_gate(msg, ppv_movie, free_user)
    assert msg.calls[0][0] == "answer", "PPV movie must show the unlock gate, never the raw file"

    # PPV movie, VIP user: VIP bypasses the gate.
    msg = _RecordingMessage()
    await send_movie_or_ppv_gate(msg, ppv_movie, vip_user)
    assert msg.calls[0][0].startswith("answer_"), "VIP users must get the file directly"

    print("✓ send_movie_or_ppv_gate: PPV movies never bypass the gate (the trending.py bug)")


async def check_batch_add_persists_file_type():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as session:
        svc = MovieService(session)
        added = await svc.batch_add([
            {"file_id": "vid1", "title": "A Video", "file_type": MovieFileType.VIDEO},
            {"file_id": "aud1", "title": "A Song", "file_type": MovieFileType.AUDIO},
            {"file_id": "doc1", "title": "A PDF"},  # no file_type -> must default cleanly
        ])
        await session.commit()
        assert added[0].file_type == MovieFileType.VIDEO
        assert added[1].file_type == MovieFileType.AUDIO
        assert added[2].file_type == MovieFileType.DOCUMENT

        fetched = await svc.get_by_file_id("aud1")
        assert fetched.file_type == MovieFileType.AUDIO, "file_type must round-trip through a real session"

    await engine.dispose()
    print("✓ MovieService.batch_add: file_type persists and round-trips through the DB")


if __name__ == "__main__":
    check_resolve_media()
    check_ppv_unlock_keyboard()
    asyncio.run(check_deliver_movie_dispatch())
    asyncio.run(check_ppv_gate())
    asyncio.run(check_batch_add_persists_file_type())
    print("\nAll search/PPV/wallet checks passed.")
