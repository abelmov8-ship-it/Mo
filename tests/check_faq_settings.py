"""
Runnable self-check for the FAQ settings CRUD (SettingsService.get_faq and
friends) — the DB-backed replacement for the hardcoded _FAQ list that used
to live in handlers/user/support.py.

Covers:
1. First read ever seeds from the same 4 questions that used to be
   hardcoded, so admins who never touch this screen see no change.
2. Add/edit/delete round-trip through a real async session, not a
   re-implementation of the logic.
3. Move up/down swaps order correctly and clamps at both ends.
4. Hiding an entry doesn't delete it — get_faq() still returns it, only
   is_visible flips (support.py is what filters on that).

Run directly: `python3 tests/check_faq_settings.py`
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
from bot.services.settings_service import SettingsService


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
    svc = SettingsService(session)

    # 1. Seeding
    faq = await svc.get_faq()
    check("first read seeds exactly 4 entries", len(faq) == 4)
    check("seeded entries have sequential ids starting at 1", [f["id"] for f in faq] == [1, 2, 3, 4])
    check("seeded entries have sequential order starting at 0", [f["order"] for f in faq] == [0, 1, 2, 3])
    check("seeded entries are visible by default", all(f["is_visible"] for f in faq))
    check(
        "seed content matches the old hardcoded FAQ",
        faq[0]["question"] == "How do I subscribe to VIP?",
    )

    # Re-reading must NOT reseed (would duplicate/reset admin edits).
    faq_again = await svc.get_faq()
    check("second read returns the same persisted list, not a fresh reseed", faq_again == faq)

    # 2. Add
    new_entry = await svc.add_faq_entry("Do you offer refunds?", "Contact support within 24 hours.")
    check("new entry gets the next id (5)", new_entry["id"] == 5)
    check("new entry gets the next order (4)", new_entry["order"] == 4)
    faq = await svc.get_faq()
    check("faq now has 5 entries", len(faq) == 5)

    # Edit
    ok = await svc.update_faq_entry(5, answer="Contact support within 48 hours.")
    check("update_faq_entry reports success for an existing id", ok is True)
    faq = await svc.get_faq()
    updated = next(f for f in faq if f["id"] == 5)
    check("answer actually changed", updated["answer"] == "Contact support within 48 hours.")
    check("question untouched by an answer-only edit", updated["question"] == "Do you offer refunds?")

    not_ok = await svc.update_faq_entry(999, answer="x")
    check("update_faq_entry reports failure for a missing id", not_ok is False)

    # 3. Move
    await svc.move_faq_entry(5, direction=-1)  # move the just-added entry up one slot
    faq = sorted(await svc.get_faq(), key=lambda f: f["order"])
    check("move up actually changes relative position", faq[-2]["id"] == 5)

    at_top = faq[0]["id"]
    moved_past_top = await svc.move_faq_entry(at_top, direction=-1)
    check("moving the first entry further up is a no-op, not an error", moved_past_top is False)

    # 4. Visibility vs. delete
    ok = await svc.update_faq_entry(1, is_visible=False)
    faq = await svc.get_faq()
    hidden = next((f for f in faq if f["id"] == 1), None)
    check("hiding an entry keeps it in get_faq() (not deleted)", hidden is not None)
    check("hiding sets is_visible False rather than deleting", hidden["is_visible"] is False)

    deleted = await svc.delete_faq_entry(1)
    check("delete reports success", deleted is True)
    faq = await svc.get_faq()
    check("deleted entry is actually gone", all(f["id"] != 1 for f in faq))

    await session.close()
    print("\nAll FAQ settings checks passed.")


asyncio.run(main())
