from datetime import datetime, timezone

from app.api.analytics import period_start


def test_period_start_uses_calendar_months_and_weeks():
    now = datetime(2026, 3, 31, 12, 30, tzinfo=timezone.utc)

    assert period_start("all", now) is None
    assert period_start("week", now) == datetime(2026, 3, 24, 12, 30, tzinfo=timezone.utc)
    assert period_start("month", now) == datetime(2026, 2, 28, 12, 30, tzinfo=timezone.utc)
    assert period_start("year", now) == datetime(2025, 3, 31, 12, 30, tzinfo=timezone.utc)


def test_period_start_clamps_leap_day_for_previous_year():
    now = datetime(2024, 2, 29, 8, 0, tzinfo=timezone.utc)

    assert period_start("year", now) == datetime(2023, 2, 28, 8, 0, tzinfo=timezone.utc)
