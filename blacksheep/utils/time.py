import sys
from datetime import MINYEAR, datetime, timezone

UTC = timezone.utc

MIN_DATETIME = datetime(MINYEAR, 1, 1, tzinfo=None)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
