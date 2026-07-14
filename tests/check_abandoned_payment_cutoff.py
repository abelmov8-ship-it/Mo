"""
Runnable self-check for _is_abandoned (tasks/abandoned_payment.py).

The SQL query in run_abandoned_payment_reminder re-expresses this same rule
as `created_at <= now - cutoff` so the DB can use an index; this checks the
boundary math the two are supposed to agree on (exactly-at-cutoff counts as
abandoned, one second under does not) so they can't silently drift apart.

Run directly: `python3 tests/check_abandoned_payment_cutoff.py`
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bot.tasks.abandoned_payment import _is_abandoned  # noqa: E402

NOW = datetime(2026, 7, 10, 12, 0, 0, tzinfo=timezone.utc)


def check(label: str, condition: bool) -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        raise SystemExit(1)


check(
    "just created (0 minutes old) is not abandoned",
    not _is_abandoned(NOW, NOW, cutoff_minutes=15),
)
check(
    "14 minutes old is not yet abandoned",
    not _is_abandoned(NOW - timedelta(minutes=14), NOW, cutoff_minutes=15),
)
check(
    "exactly at the 15-minute cutoff counts as abandoned",
    _is_abandoned(NOW - timedelta(minutes=15), NOW, cutoff_minutes=15),
)
check(
    "well past the cutoff (1 hour old) is abandoned",
    _is_abandoned(NOW - timedelta(hours=1), NOW, cutoff_minutes=15),
)
check(
    "a different cutoff value is respected (5 minutes)",
    _is_abandoned(NOW - timedelta(minutes=6), NOW, cutoff_minutes=5),
)

print("\nAll abandoned-payment cutoff checks passed.")
