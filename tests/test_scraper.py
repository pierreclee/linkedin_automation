import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timedelta
import pytest
from scraper import _parse_relative_time


@pytest.mark.parametrize("time_str,expected_delta", [
    ("5m", timedelta(minutes=5)),
    ("30m", timedelta(minutes=30)),
    ("2h", timedelta(hours=2)),
    ("1d", timedelta(days=1)),
    ("3j", timedelta(days=3)),
    ("2s", timedelta(days=365)),   # semaines → very old
    ("1a", timedelta(days=365)),   # années → very old
])
def test_parse_relative_time(time_str, expected_delta):
    before = datetime.utcnow()
    result = _parse_relative_time(time_str)
    after = datetime.utcnow()
    expected = before - expected_delta
    # Allow 2s of clock drift
    assert abs((result - expected).total_seconds()) < 2


def test_parse_relative_time_unknown_returns_now():
    before = datetime.utcnow()
    result = _parse_relative_time("xyz")
    after = datetime.utcnow()
    assert before <= result <= after
