"""Validate Hub report values without treating receipt time as measurement time."""

from datetime import UTC, datetime
from math import isfinite

# Beszel containers collection fields, sorted by source field.
CONTAINER_CPU = "cpu"
CONTAINER_HEALTH = "health"
CONTAINER_MEMORY = "memory"
CONTAINER_NET = "net"
CONTAINER_UPDATED = "updated"

HEALTH_OPTIONS = ["no_health_data", "starting", "healthy", "unhealthy", "unknown"]


def finite_number(value):
    """Accept finite JSON numbers only; bool is not a metric."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except OverflowError, ValueError:
        return None
    return number if isfinite(number) else None


def statistics_timestamp(value, now):
    """Parse a valid aware Hub statistics record time, including old records."""
    if not isinstance(value, str):
        return None
    try:
        timestamp = datetime.fromisoformat(value)
    except ValueError:
        return None
    if timestamp.tzinfo is None or timestamp > now:
        return None
    return timestamp.astimezone(UTC)


def container_timestamp(value, now):
    """Parse a numeric Unix millisecond Hub receipt time, never the poll time."""
    number = finite_number(value)
    if number is None or number <= 0:
        return None
    try:
        timestamp = datetime.fromtimestamp(number / 1000, UTC)
    except OverflowError, OSError, ValueError:
        return None
    return timestamp if timestamp <= now else None


def container_value(record, key, now):
    """Normalize a container report with explicit missing and health semantics."""
    if key == CONTAINER_UPDATED:
        return container_timestamp(record.get(key), now)
    number = finite_number(record.get(key))
    if key == CONTAINER_HEALTH:
        if number is None or number not in (0, 1, 2, 3):
            return "unknown"
        return HEALTH_OPTIONS[int(number)]
    if number is None or number < 0:
        return None
    if key == CONTAINER_CPU and number > 100:
        return None
    if key == CONTAINER_MEMORY:
        number *= 1024**2 / 1_000_000
    return round(number, 2) if isfinite(number) else None
