"""Tests for the Layer 4 Julian Day conversion."""

from datetime import datetime, timedelta, timezone

import pytest

from vedic_chart.time.julian_day import julian_day_ut


def test_j2000_epoch():
    moment = datetime(2000, 1, 1, 12, 0, tzinfo=timezone.utc)
    assert julian_day_ut(moment) == 2451545.0


def test_unix_epoch():
    moment = datetime(1970, 1, 1, 0, 0, tzinfo=timezone.utc)
    assert julian_day_ut(moment) == 2440587.5


def test_naive_datetime_rejected():
    with pytest.raises(ValueError):
        julian_day_ut(datetime(2000, 1, 1, 12, 0))


def test_non_utc_aware_datetime_is_converted():
    india = timezone(timedelta(hours=5, minutes=30))
    local = datetime(2000, 1, 1, 17, 30, tzinfo=india)
    utc = datetime(2000, 1, 1, 12, 0, tzinfo=timezone.utc)
    assert julian_day_ut(local) == julian_day_ut(utc)
