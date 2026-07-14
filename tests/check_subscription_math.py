"""
Runnable self-check for the VIP-stacking math in subscription_service.py.

This is the single most-repeated piece of non-trivial logic touched in this
change set — it backs grant_vip, activate (Chapa/Bank/wallet purchases), and
extend (referral rewards, promo redemption, admin Grant VIP Days). A
regression here silently shortens or erases VIP time for anyone who already
had some, which is exactly the kind of bug that doesn't show up until a
real user complains.

Run directly: `python3 tests/check_subscription_math.py` — no pytest,
no fixtures, no DB. Imports the real function so it actually exercises
production code, not a re-implementation of it.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bot.services.subscription_service import _stacked_expiry  # noqa: E402

NOW = datetime(2026, 6, 30, 12, 0, 0, tzinfo=timezone.utc)


def check(label: str, condition: bool) -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        raise SystemExit(1)


# No existing subscription: 7 new days from now.
result = _stacked_expiry(NOW, 7, None)
check("fresh grant starts from now", result == NOW + timedelta(days=7))

# Existing subscription still has 10 days left: a 7-day grant should land
# on top of the remaining time (17 days out), not overwrite it with a
# shorter 7-day window.
existing_expiry = NOW + timedelta(days=10)
result = _stacked_expiry(NOW, 7, existing_expiry)
check(
    "stacks onto remaining time instead of overwriting it",
    result == NOW + timedelta(days=17),
)

# Existing subscription already expired 3 days ago: should NOT grant from
# the stale expiry (which would silently lose 3 days) — base must be "now".
expired = NOW - timedelta(days=3)
result = _stacked_expiry(NOW, 7, expired)
check(
    "an already-expired sub doesn't get backdated time",
    result == NOW + timedelta(days=7),
)

# Existing subscription expires at exactly "now" — boundary case, should
# behave the same as "no remaining time": 7 fresh days, not 0.
result = _stacked_expiry(NOW, 7, NOW)
check("expiry exactly equal to now adds fresh days, not zero", result == NOW + timedelta(days=7))

print("\nAll subscription stacking checks passed.")
