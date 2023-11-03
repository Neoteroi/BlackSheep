import sys
from datetime import MINYEAR, datetime, timezone

UTC = timezone.utc

MIN_DATETIME = datetime(MINYEAR, 1, 1, tzinfo=None)


def utcnow() -> datetime:
    if sys.version_info < (3, 12):
        return datetime.utcnow()
    return datetime.now(UTC).replace(tzinfo=None)
