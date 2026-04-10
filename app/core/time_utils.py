from datetime import datetime, timezone, timedelta

# AEST is UTC+10 (or +11 during Daylight Savings)
# We can use zoneinfo for automatic handling if installed
try:
    from zoneinfo import ZoneInfo

    SYDNEY_TZ = ZoneInfo("Australia/Sydney")
except ImportError:
    # Fallback to fixed offset if zoneinfo isn't available
    SYDNEY_TZ = timezone(timedelta(hours=10))


def now_utc() -> datetime:
    """Return the current aware UTC datetime."""
    return datetime.now(timezone.utc)


def to_aest(dt: datetime) -> datetime:
    """Converts a UTC aware datetime to Sydney time for display."""
    return dt.astimezone(SYDNEY_TZ)


def to_aware(dt: datetime) -> datetime:
    """Convert a naive datetime to an aware UTC datetime."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def format_log_time() -> str:
    """Used by the logger to print the AEST timestamp."""
    return now_utc().astimezone(SYDNEY_TZ).strftime("%Y-%m-%d %H:%M:%S AEST")
