"""
Runnable self-check for the router-registration-order fix in main.py.

search.router contains a catch-all message handler (any non-command,
non-"search button" text -> treated as a movie query). aiogram tries
included routers in registration order and stops at the first matching
handler, so if search.router is included before the routers that own
specific reply-keyboard buttons, every button tap gets swallowed by the
catch-all and answered with "no results, request movie" instead of doing
its actual job. This guards against that regressing.

ponytail: this checks *source order of the include_router() calls*, not
live aiogram routing semantics (aiogram isn't installed in this sandbox,
so a real Dispatcher.feed_update test isn't runnable here). If another
router ever grows its own catch-all F.text handler, this check won't
catch it — the real fix there is the same one applied here: keep any
catch-all router last.

Run directly: `python3 tests/check_router_order.py`
"""
import re
import sys
from pathlib import Path

MAIN_PY = Path(__file__).resolve().parents[1] / "src" / "bot" / "main.py"


def check(label: str, condition: bool) -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        raise SystemExit(1)


source = MAIN_PY.read_text()
includes = re.findall(r"dp\.include_router\((\w+)\.router\)", source)

check("main.py has router registrations to check", len(includes) > 0)
check(
    "search router is the last one registered",
    includes[-1] == "search",
)
check(
    "search router is registered after every other user/admin router",
    includes.index("search") == len(includes) - 1,
)

print(f"\nRegistration order: {' -> '.join(includes)}")
print("All router order checks passed.")
