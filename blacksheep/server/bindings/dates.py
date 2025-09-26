from datetime import datetime


def parse_datetime(value: str) -> datetime:
    """
    This function parse ISO 8601 datetime strings.
    It only supports the most common ISO formats:

    - "%Y-%m-%dT%H:%M:%S.%f"
    - "%Y-%m-%dT%H:%M:%S"
    - "%Y-%m-%d"
    """
    value_len = len(value)
    # The following functions, unlike fromisoformat, accept parts without leading 0.
    # Try parsing with microseconds (minimum length: 16, like in "2025-6-9T8:6:3.1")
    if value_len >= 16:
        try:
            return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%f")
        except ValueError:
            pass

    # Try parsing without microseconds (minimum length: 14, like in "2025-6-9T8:6:3")
    if value_len >= 14:
        try:
            return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            pass

    # Try parsing date only (minimum length: 8, like in "2025-6-9")
    if value_len >= 8:
        try:
            return datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            pass

    raise ValueError("Could not parse datetime string.")
