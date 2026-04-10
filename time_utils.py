from datetime import datetime, timezone, timedelta

# AEST is UTC+10 (or +11 during Daylight Savings)
# We can use zoneinfo for automatic handling if installed
try:
    from zoneinfo import ZoneInfo
    SYDNEY_TZ = ZoneInfo("Australia/Sydney")
except ImportError:
    SYDNEY_TZ = timezone(timedelta(hours=10))

