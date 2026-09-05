"""Layer 4: conversion from an exact UTC instant to a Julian Day in UT.

Pure Python. This module deliberately imports nothing beyond the standard
library -- in particular it never touches ``swisseph`` or Layer 5, so the
calendar arithmetic can be reasoned about and tested on its own.

Two documented approximations apply:

* **UTC is used as UT1.** The Julian Day produced here is labelled "UT" and is
  computed from UTC. UT1 and UTC are kept within 0.9 s of each other by leap
  seconds, which bounds the resulting positional error at roughly 0.00015 deg
  even for the Moon, the fastest-moving body. That is far below the precision
  any chart interpretation depends on.
* **The calendar is proleptic Gregorian.** Python's ``datetime`` extends the
  Gregorian calendar backwards past its 1582 adoption. Dates before then will
  not match Julian-calendar civil records.
"""

from datetime import datetime, timezone

# Julian Day number of the Unix epoch, 1970-01-01 00:00:00 UTC.
UNIX_EPOCH_JD = 2440587.5

SECONDS_PER_DAY = 86400.0


def julian_day_ut(moment: datetime) -> float:
    """Return the Julian Day (UT) of a timezone-aware datetime.

    Any timezone-aware datetime is accepted and converted to UTC internally.
    Naive datetimes are rejected: a chart depends on an exact instant, and
    guessing a local zone here would silently corrupt every position.
    """
    if moment.tzinfo is None or moment.tzinfo.utcoffset(moment) is None:
        raise ValueError(
            "julian_day_ut requires a timezone-aware datetime; "
            "pass an explicit UTC moment, e.g. "
            "datetime(2000, 1, 1, 12, tzinfo=timezone.utc)."
        )

    moment_utc = moment.astimezone(timezone.utc)
    return moment_utc.timestamp() / SECONDS_PER_DAY + UNIX_EPOCH_JD
