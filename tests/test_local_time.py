"""Tests for the Layer 3 local-time normalization.

Pure stdlib: no ephemeris files and no ephemeris fixture are needed.
"""

from datetime import date, datetime, time, timezone

import pytest

from vedic_chart.time.julian_day import julian_day_ut
from vedic_chart.time.local_time import (
    AmbiguousLocalTimeError,
    InvalidTimezoneError,
    NonexistentLocalTimeError,
    normalize_birth_time,
)


def test_india_standard_time():
    result = normalize_birth_time(
        date(1990, 5, 15), time(14, 30, 45), "Asia/Kolkata"
    )
    assert result == datetime(1990, 5, 15, 9, 0, 45, tzinfo=timezone.utc)
    assert result.tzinfo is timezone.utc


def test_seconds_and_microseconds_are_preserved():
    result = normalize_birth_time(
        date(2000, 1, 1), time(6, 15, 30, 123456), "Asia/Kolkata"
    )

    assert result == datetime(2000, 1, 1, 0, 45, 30, 123456, tzinfo=timezone.utc)
    # Nothing is rounded or snapped on the way through.
    assert result.second == 30
    assert result.microsecond == 123456


def test_dst_zone_uses_standard_offset_in_winter():
    result = normalize_birth_time(
        date(2023, 1, 15), time(12, 0), "America/New_York"
    )
    assert result == datetime(2023, 1, 15, 17, 0, tzinfo=timezone.utc)


def test_dst_zone_uses_daylight_offset_in_summer():
    result = normalize_birth_time(
        date(2023, 7, 15), time(12, 0), "America/New_York"
    )
    assert result == datetime(2023, 7, 15, 16, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "timezone_id",
    [
        "Asia/Kolkatta",  # misspelled
        "",
        "EST5EDT-madeup",
        "Not/AZone",
    ],
)
def test_invalid_timezone_identifiers(timezone_id):
    with pytest.raises(InvalidTimezoneError):
        normalize_birth_time(date(2000, 1, 1), time(12, 0), timezone_id)


def test_invalid_timezone_message_names_the_identifier():
    with pytest.raises(InvalidTimezoneError, match="Asia/Kolkatta"):
        normalize_birth_time(date(2000, 1, 1), time(12, 0), "Asia/Kolkatta")


def test_non_string_timezone_rejected():
    with pytest.raises(InvalidTimezoneError):
        normalize_birth_time(date(2000, 1, 1), time(12, 0), 5.5)


def test_nonexistent_local_time_is_rejected():
    # 2023-03-12 02:30 never happened in New York: the clock went 01:59 -> 03:00.
    with pytest.raises(NonexistentLocalTimeError) as excinfo:
        normalize_birth_time(
            date(2023, 3, 12), time(2, 30), "America/New_York"
        )

    message = str(excinfo.value)
    assert "-05:00" in message and "-04:00" in message
    assert "America/New_York" in message


def test_ambiguous_local_time_is_rejected():
    # 2023-11-05 01:30 happened twice in New York.
    with pytest.raises(AmbiguousLocalTimeError) as excinfo:
        normalize_birth_time(
            date(2023, 11, 5), time(1, 30), "America/New_York"
        )

    message = str(excinfo.value)
    assert "-04:00" in message and "-05:00" in message
    assert "America/New_York" in message


def test_aware_birth_time_is_rejected():
    with pytest.raises(ValueError):
        normalize_birth_time(
            date(2000, 1, 1), time(12, 0, tzinfo=timezone.utc), "Asia/Kolkata"
        )


def test_custom_errors_are_value_errors():
    for error_type in (
        InvalidTimezoneError,
        NonexistentLocalTimeError,
        AmbiguousLocalTimeError,
    ):
        assert issubclass(error_type, ValueError)


def test_feeds_layer_four():
    # 17:30 IST on 2000-01-01 is 12:00 UTC, the J2000 epoch.
    moment = normalize_birth_time(
        date(2000, 1, 1), time(17, 30), "Asia/Kolkata"
    )
    assert julian_day_ut(moment) == 2451545.0


def test_historical_india_war_time():
    """India ran +06:30 during the second world war.

    Confirmed present in this machine's tzdata before the test was written.
    Historical offsets come from the OS tzdata database, so this asserts what
    the installed database says rather than an independent authority.
    """
    result = normalize_birth_time(
        date(1943, 1, 1), time(12, 0), "Asia/Kolkata"
    )
    assert result == datetime(1943, 1, 1, 5, 30, tzinfo=timezone.utc)

    # And back to +05:30 after the war.
    post_war = normalize_birth_time(
        date(1946, 1, 1), time(12, 0), "Asia/Kolkata"
    )
    assert post_war == datetime(1946, 1, 1, 6, 30, tzinfo=timezone.utc)
