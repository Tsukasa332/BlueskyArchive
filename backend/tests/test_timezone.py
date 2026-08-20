from datetime import datetime, timezone

from app.api.query_helpers import date_range, local_created_at, timeline_ordering
from app.core.config import settings
from archive.db.models import Post


def test_date_range_uses_configured_app_timezone(monkeypatch):
    monkeypatch.setattr(settings, "app_timezone", "UTC")
    start, end = date_range(2026, 7, 11)
    assert start == datetime(2026, 7, 11, tzinfo=timezone.utc)
    assert end == datetime(2026, 7, 12, tzinfo=timezone.utc)


def test_calendar_timezone_expression_uses_configured_app_timezone(monkeypatch):
    monkeypatch.setattr(settings, "app_timezone", "Europe/London")
    compiled = str(local_created_at(Post.record_created_at).compile(compile_kwargs={"literal_binds": True}))
    assert "Europe/London" in compiled


def test_day_ascending_order_uses_configured_local_date(monkeypatch):
    monkeypatch.setattr(settings, "app_timezone", "Asia/Tokyo")
    ordering = timeline_ordering(Post.record_created_at, Post.indexed_at, "day_asc", Post.id)
    compiled = [str(clause.compile(compile_kwargs={"literal_binds": True})) for clause in ordering]
    assert "Asia/Tokyo" in compiled[0]
    assert "DESC NULLS LAST" in compiled[0]
    assert "ASC NULLS LAST" in compiled[1]
