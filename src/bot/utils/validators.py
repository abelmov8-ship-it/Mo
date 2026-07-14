"""Input validation helpers used across handlers."""
from __future__ import annotations

import re
from datetime import datetime


def is_positive_number(text: str) -> tuple[bool, float]:
    """Returns (valid, value)."""
    try:
        val = float(text.strip())
        return val > 0, val
    except ValueError:
        return False, 0.0


def is_positive_int(text: str) -> tuple[bool, int]:
    try:
        val = int(text.strip())
        return val > 0, val
    except ValueError:
        return False, 0


def is_valid_telegram_id(text: str) -> tuple[bool, int]:
    try:
        val = int(text.strip())
        return 10_000 <= val <= 9_999_999_999, val
    except ValueError:
        return False, 0


def is_valid_url(text: str) -> bool:
    pattern = re.compile(
        r"^(https?://)?(t\.me/|@)[a-zA-Z0-9_+/]+$"
    )
    return bool(pattern.match(text.strip()))


def parse_date(text: str) -> datetime | None:
    """Parses dates in YYYY-MM-DD format."""
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(text.strip(), fmt)
        except ValueError:
            continue
    return None


def sanitize(text: str, max_length: int = 256) -> str:
    return text.strip()[:max_length]
