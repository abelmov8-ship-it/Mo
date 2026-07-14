"""
Runnable self-check for Settings.parse_admin_ids in config.py.

pydantic-settings JSON-decodes complex-typed (list, dict, ...) env values
before validators see them. A single admin ID with no comma
(ADMIN_IDS=123456789) is valid JSON on its own -> it arrives at the
validator as a bare int, not a str or list. The old validator only
branched on list/str and silently returned [] for anything else, which
made every "is this user an admin?" check fail for single-admin setups
(the Admin Panel button hidden, IsAdmin filter always False) with no
error anywhere.

Requires the project's real dependencies (aiogram/pydantic-settings) to
be installed, since it imports the actual Settings class rather than
re-implementing the parsing logic. If they aren't installed, this
prints a note and exits 0 rather than failing the run for an unrelated
environment reason.

Run directly: `python3 tests/check_admin_ids_parsing.py`
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def check(label: str, condition: bool) -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        raise SystemExit(1)


try:
    import os
    os.environ.setdefault("BOT_TOKEN", "test-token-not-real")
    from bot.config import Settings  # noqa: E402
except ModuleNotFoundError as exc:
    print(f"SKIP: dependency not installed in this environment ({exc}). "
          "Run inside the project's venv to actually exercise this check.")
    sys.exit(0)

parse = Settings.parse_admin_ids.__func__

# The bug: a lone admin ID, no comma -> pydantic-settings' env source hands
# the validator a bare int (this is what json.loads("123456789") produces).
check(
    "single admin ID (arrives as bare int) is not silently dropped",
    parse(Settings, 123456789) == [123456789],
)

# Multi-ID comma string never round-trips through JSON, so it always
# arrives as a raw string — must keep working.
check(
    "comma-separated string of multiple IDs still parses",
    parse(Settings, "111,222, 333") == [111, 222, 333],
)

# Already-a-list (e.g. ADMIN_IDS=[111,222] in .env, valid JSON array) passes through.
check(
    "JSON array value passes through unchanged",
    parse(Settings, [111, 222]) == [111, 222],
)

# Empty/unset stays empty rather than erroring.
check("empty string yields empty list", parse(Settings, "") == [])

print("\nAll ADMIN_IDS parsing checks passed.")
