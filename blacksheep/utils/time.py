import sys
from datetime import datetime, MINYEAR, timezone

UTC = timezone.utc

MIN_DATETIME = datetime(MINYEAR, 1, 1, tzinfo=None)


def utcnow() -> datetime:
    if sys.version_info < (3, 12):
        return datetime.utcnow()
    return datetime.now(UTC).astimezone(None).replace(tzinfo=None)
