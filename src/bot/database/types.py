from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator):
    """
    DateTime(timezone=True) that actually round-trips as UTC-aware,
    regardless of backend.

    ponytail: SQLite (our default DATABASE_URL) has no native tz-aware
    datetime type. SQLAlchemy's sqlite dialect stores/reads DateTime as a
    plain ISO string and always hands back a *naive* datetime on SELECT,
    even when the column is declared DateTime(timezone=True). Every
    subtraction or comparison against datetime.now(timezone.utc) (aware)
    then raises "TypeError: can't subtract offset-naive and offset-aware
    datetimes" -- this is what broke the Profile screen's expiry display.
    This type re-attaches UTC tzinfo on the way out of the DB, and
    normalizes to UTC on the way in, so callers never have to think about
    it again. On a backend that does preserve tzinfo (e.g. Postgres) this
    is a no-op.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
