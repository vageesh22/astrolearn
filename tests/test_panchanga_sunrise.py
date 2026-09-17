"""Layer 16's sunrise adapter (specification sections 2.4, 3.2 and 6).

The sky is **injected** throughout this file. ``find_sunrise_window`` takes a
``rise_after`` callable, so the bracketing, the ``<=`` semantics at exact
sunrise and the three refusals can be exercised on Julian Days chosen to the
last bit, with no ephemeris open and nothing that depends on where the Sun
actually was. The real sunrise gets its own tests in
``tests/test_panchanga_compute.py``, where the ephemeris is the point.

Two things make the synthetic sunrises exact rather than approximate. First,
every instant is turned into a Julian Day with the FROZEN ``julian_day_ut`` and
the synthetic sunrises are then placed **relative to that float** -- at ``t``
itself, at ``nextafter(t, ...)``, at whole days either side -- so "exactly at
sunrise" means exactly, and "one ULP before" means one ULP. Second, nothing is
asserted about a datetime where a Julian Day will do: the Julian Day is the
value the comparison was made on, and the datetime beside it is a conversion.

One block at the end is the exception and says so: the Tromso regression and
the genuinely-unavailable polar cases need the real library, because what they
pin is what a ``None`` from it actually means.

The zone tests are the other half. A vara is the weekday of the **local civil
date of the previous sunrise**, so the cases that matter are the ones where
that date is not the obvious one: a pre-dawn birth whose UTC date, local date
and vara are three different answers; a DST zone on both of its transition days;
and a zone fourteen hours ahead of UTC, where the local date is tomorrow's.
"""

import dataclasses
import math
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from vedic_chart.panchanga import (
    InvalidTimezoneError,
    SunriseUnavailable,
    SunriseWindow,
    Vara,
    find_sunrise_window,
)
import vedic_chart.panchanga.sunrise as sunrise_module
from vedic_chart.panchanga.sunrise import (
    MAX_BACKTRACK_DAYS,
    MAX_CONSECUTIVE_GAP_DAYS,
    MAX_PROBES,
    REASON_NO_NEXT_SUNRISE,
    REASON_NO_PREVIOUS_SUNRISE,
    REASON_SUNRISES_NOT_CONSECUTIVE,
    SEARCH_SPAN_DAYS,
    SEARCH_STEP_DAYS,
    SUNRISE_CONVENTION,
    UNAVAILABLE_REASONS,
    datetime_from_julian_day,
    default_rise_after,
    resolve_zone,
    utc_instant,
    vara_from_sunrise,
)
from render_helpers import EPHE_DIR
from vedic_chart.astronomy.positions import ephemeris_session
from vedic_chart.time.julian_day import julian_day_ut
from vedic_chart.vedic.grahas import Graha

IST = timezone(timedelta(hours=5, minutes=30))

#: A place; the injected sky ignores it, and the tests that care about a place
#: say so.
SOMEWHERE = (31.32556, 75.57917, "Asia/Kolkata")


def sky(*sunrises):
    """A ``rise_after`` over a fixed list of sunrise Julian Days.

    Returns the first sunrise at or after the Julian Day asked for, and None
    when there is none -- which is what the Layer 5 accessor returns when the
    library reports a circumpolar Sun.
    """
    ordered = sorted(sunrises)

    def rise_after(julian_day, latitude, longitude):
        for sunrise in ordered:
            if sunrise >= julian_day:
                return sunrise
        return None

    return rise_after


#: The library's slow method searches a 28-hour window from two hours before
#: the probe (specification 2.3 and 3.2); a synthetic sky that models that
#: window is the only way to reproduce the Tromso shape without an ephemeris.
LIBRARY_WINDOW_DAYS = 28.0 / 24.0


def windowed_sky(*sunrises, window=LIBRARY_WINDOW_DAYS):
    """A ``rise_after`` that can only see ``window`` days past its probe.

    This is what the real accessor does beyond 65 degrees: it reports the first
    sunrise at or after the probe **if it falls inside the library's search
    window**, and None otherwise. A None is therefore one probe's silence and
    says nothing about the rest of the span.
    """
    ordered = sorted(sunrises)

    def rise_after(julian_day, latitude, longitude):
        for sunrise in ordered:
            if sunrise >= julian_day:
                return sunrise if sunrise - julian_day <= window else None
        return None

    return rise_after


def counting_calls(inner):
    """Wrap any ``rise_after`` so the probes it was asked about are recorded."""
    calls = []

    def rise_after(julian_day, latitude, longitude):
        calls.append(julian_day)
        return inner(julian_day, latitude, longitude)

    return rise_after, calls


def counting_sky(*sunrises):
    """The same, with the Julian Days it was asked about recorded."""
    calls = []
    inner = sky(*sunrises)

    def rise_after(julian_day, latitude, longitude):
        calls.append(julian_day)
        return inner(julian_day, latitude, longitude)

    return rise_after, calls


def at(year, month, day, hour=0, minute=0, second=0, zone=timezone.utc):
    return datetime(year, month, day, hour, minute, second, tzinfo=zone)


def jd(moment):
    return julian_day_ut(moment)


def window_for(moment, rise_after, latitude=0.0, longitude=0.0, zone="UTC"):
    return find_sunrise_window(
        moment, latitude, longitude, zone, rise_after=rise_after
    )


# --- the <= semantics at a sunrise (decision D5) ---------------------------


def test_an_instant_between_two_sunrises_takes_the_earlier_one():
    moment = at(2024, 5, 10, 9, 0)
    t = jd(moment)
    window = window_for(moment, sky(t - 1.0, t + 0.25, t + 1.25))

    assert isinstance(window, SunriseWindow)
    assert window.previous_julian_day_ut == t - 1.0
    assert window.next_julian_day_ut == t + 0.25


def test_an_instant_exactly_at_a_sunrise_belongs_to_the_new_vara():
    """Decision D5, in the float domain: the comparison is ``<=``."""
    moment = at(2024, 5, 10, 9, 0)
    t = jd(moment)
    window = window_for(moment, sky(t - 1.0, t, t + 1.0))

    assert isinstance(window, SunriseWindow)
    assert window.previous_julian_day_ut == t
    assert window.next_julian_day_ut == t + 1.0


def test_a_sunrise_one_ulp_after_the_instant_is_still_the_next_one():
    moment = at(2024, 5, 10, 9, 0)
    t = jd(moment)
    just_after = math.nextafter(t, math.inf)
    window = window_for(moment, sky(t - 1.0, just_after, t + 1.0))

    assert isinstance(window, SunriseWindow)
    assert window.previous_julian_day_ut == t - 1.0
    assert window.next_julian_day_ut == just_after


def test_a_sunrise_one_ulp_before_the_instant_is_already_the_previous_one():
    moment = at(2024, 5, 10, 9, 0)
    t = jd(moment)
    just_before = math.nextafter(t, -math.inf)
    window = window_for(moment, sky(t - 1.0, just_before, t + 1.0))

    assert isinstance(window, SunriseWindow)
    assert window.previous_julian_day_ut == just_before
    assert window.next_julian_day_ut == t + 1.0


def test_the_three_neighbouring_floats_give_the_two_possible_answers():
    """One ULP either side of equality, and equality itself, in one place."""
    moment = at(2024, 5, 10, 9, 0)
    t = jd(moment)

    for offset, expected_previous in (
        (math.nextafter(t, -math.inf), math.nextafter(t, -math.inf)),
        (t, t),
        (math.nextafter(t, math.inf), t - 1.0),
    ):
        window = window_for(moment, sky(t - 1.0, offset, t + 1.0))
        assert window.previous_julian_day_ut == expected_previous


# --- the bracketing loop ---------------------------------------------------


def test_the_search_starts_two_days_back_and_steps_half_a_day():
    moment = at(2024, 5, 10, 9, 0)
    t = jd(moment)
    rise_after, calls = counting_sky(t - 2.5, t - 1.5, t - 0.5, t + 0.5)

    window = window_for(moment, rise_after)

    assert calls[0] == t - SEARCH_SPAN_DAYS
    assert calls[1:] == [t - 1.5 + 0.5, t - 0.5 + 0.5]
    assert window.previous_julian_day_ut == t - 0.5
    assert window.next_julian_day_ut == t + 0.5


def test_the_loops_are_bounded_by_a_constant():
    """``MAX_PROBES`` bounds each phase, and daily sunrises stay well inside it."""
    moment = at(2024, 5, 10, 9, 0)
    t = jd(moment)
    rise_after, calls = counting_sky(*[t - 2.0 + 0.3 + n for n in range(6)])

    find_sunrise_window(moment, 0.0, 0.0, "UTC", rise_after=rise_after)

    assert len(calls) <= MAX_PROBES
    assert len(calls) <= 5
    # The derivation: neither probe travels further than span + gap, at a step
    # a time, plus the probe that starts the travel.
    # An upper bound with margin, not an exact fit: the guaranteed advance per
    # iteration is a step minus the library's two-hour look-back, so each phase
    # needs at most ceil(2.0 / 0.4167) = 5.
    assert MAX_PROBES == 9
    guaranteed_advance = SEARCH_STEP_DAYS - 2.0 / 24.0
    assert math.ceil(SEARCH_SPAN_DAYS / guaranteed_advance) <= MAX_PROBES
    assert math.ceil(
        (MAX_CONSECUTIVE_GAP_DAYS - SEARCH_STEP_DAYS) / guaranteed_advance
    ) <= MAX_PROBES


def test_an_empty_sky_costs_only_the_probes_that_sweep_the_span():
    """A silent sky is swept, not given up on after one probe."""
    moment = at(2024, 5, 10, 9, 0)
    t = jd(moment)
    rise_after, calls = counting_sky()

    result = window_for(moment, rise_after, latitude=80.0)

    assert isinstance(result, SunriseUnavailable)
    assert calls == [t - 2.0, t - 1.5, t - 1.0, t - 0.5, t]
    assert len(calls) < MAX_PROBES


def test_the_probe_bound_is_a_runtime_error_not_a_hang(monkeypatch):
    """Exhausting the bound raises; it never spins.

    Unreachable with any sky that advances, because every probe moves forward
    by at least a step -- so the bound is lowered to make the check observable.
    """
    moment = at(2024, 5, 10, 9, 0)
    t = jd(moment)

    monkeypatch.setattr(sunrise_module, "MAX_PROBES", 1)

    with pytest.raises(RuntimeError, match="without reaching its limit"):
        window_for(moment, sky(*[t - 2.0 + 0.3 + n for n in range(6)]))


# --- a None is one probe's silence, not the span's -------------------------


def test_a_first_probe_that_finds_nothing_does_not_end_the_search():
    """The v0.1 bug, in miniature: the span is probed, not sampled once.

    The synthetic sky reproduces the Tromso arrangement exactly -- an isolated
    pair of sunrises, one just before the instant and one just after, with the
    span's early probes too far away to see either through the library's
    28-hour window. v0.1 read the first probe's None as "no sunrise in two
    days" and reported the day unavailable.
    """
    moment = at(2024, 5, 10, 9, 0)
    t = jd(moment)
    rise_after, calls = counting_calls(windowed_sky(t - 0.2, t + 0.8))

    window = window_for(moment, rise_after)

    assert isinstance(window, SunriseWindow)
    assert window.previous_julian_day_ut == t - 0.2
    assert window.next_julian_day_ut == t + 0.8
    # The first two probes found nothing and the search carried on regardless.
    assert calls[:3] == [t - 2.0, t - 1.5, t - 1.0]
    assert rise_after(t - 2.0, 0.0, 0.0) is None
    assert rise_after(t - 1.0, 0.0, 0.0) == t - 0.2


@pytest.mark.parametrize("offset", (-0.05, -0.2, -0.45, -0.7))
def test_silent_probes_are_survived_wherever_the_previous_sunrise_sits(offset):
    """Two Nones is the deepest silence a real window can put before a sunrise.

    A probe is silent only when the next sunrise is more than 28 hours past it.
    The probe half a day before the instant can therefore only be silent if the
    next sunrise is more than 0.667 days *after* the instant -- in which case
    there is no previous sunrise at all. So a found previous is preceded by at
    most the two probes at the far end of the span, and that is what the walk
    has to survive; it survives any number, and the all-silent sweep is tested
    separately.
    """
    t = jd(at(2024, 5, 10, 9, 0))
    rise_after, calls = counting_calls(windowed_sky(t + offset, t + offset + 1.0))

    window = window_for(at(2024, 5, 10, 9, 0), rise_after)

    assert isinstance(window, SunriseWindow)
    assert window.previous_julian_day_ut == t + offset
    assert window.next_julian_day_ut == t + offset + 1.0
    assert calls[0] == t - 2.0
    assert all(
        rise_after(probe, 0.0, 0.0) is None
        for probe in calls[:1]
    )


def test_the_phases_together_are_the_tromso_shape_without_an_ephemeris():
    """Phase A sweeps past three silent probes; phase B fetches the next one."""
    moment = at(2024, 5, 10, 9, 0)
    t = jd(moment)
    rise_after, calls = counting_calls(windowed_sky(t - 0.2, t + 0.8))

    window = window_for(moment, rise_after)

    # Phase A: two silent probes, then the previous sunrise, then the probe
    # just past it -- which is already after the instant, so the phase ends.
    assert calls[:4] == [t - 2.0, t - 1.5, t - 1.0, t - 0.2 + 0.5]
    # Phase B: exactly one more probe, from the same place, and it succeeds.
    assert len(calls) == 4
    assert window.next_julian_day_ut == t + 0.8


def test_phase_b_finds_the_next_sunrise_the_span_ran_out_before():
    """Phase A's probe passes the instant before it reaches the next sunrise.

    This is the Tromso shape: the previous sunrise sits close enough below the
    instant that ``previous + STEP`` is already past it, so phase A ends with no
    following and phase B has to go and get one.
    """
    moment = at(2024, 5, 10, 9, 0)
    t = jd(moment)
    rise_after, calls = counting_sky(t - 0.2, t + 0.8)

    window = window_for(moment, rise_after)

    assert isinstance(window, SunriseWindow)
    assert window.previous_julian_day_ut == t - 0.2
    assert window.next_julian_day_ut == t + 0.8
    # Phase A stopped at t + 0.3 (past the instant); phase B probed from there.
    assert calls[-1] == t - 0.2 + 0.5
    assert calls.count(t - 0.2 + 0.5) == 1


def test_phase_b_can_discover_a_later_previous_the_span_missed():
    """A scripted sky, because a pure one cannot answer twice differently.

    Phase B re-anchors when a probe hands back a sunrise that is still at or
    before the instant: that sunrise becomes the previous, and the walk goes on
    from just past it.
    """
    moment = at(2024, 5, 10, 9, 0)
    t = jd(moment)
    # Phase A finds t - 0.45 and its next probe (t + 0.05) is already past the
    # instant, so the phase ends with no following. Phase B probes from there,
    # gets a sunrise still at or before the instant, re-anchors on it, and only
    # then finds the next one. Every value is within a quarter day of its probe.
    answers = iter([t - 0.45, t - 0.15, t + 0.7])

    def scripted(julian_day, latitude, longitude):
        return next(answers)

    window = window_for(moment, scripted)

    assert isinstance(window, SunriseWindow)
    assert window.previous_julian_day_ut == t - 0.15
    assert window.next_julian_day_ut == t + 0.7


def test_a_half_day_step_cannot_skip_a_sunrise():
    """Sunrises a day apart: every one of them is visited in turn."""
    moment = at(2024, 5, 10, 9, 0)
    t = jd(moment)
    sunrises = [t - 1.75, t - 0.75, t + 0.25]
    rise_after, calls = counting_sky(*sunrises)

    window = window_for(moment, rise_after)

    assert window.previous_julian_day_ut == t - 0.75
    assert window.next_julian_day_ut == t + 0.25
    # Every sunrise before the instant was seen, none jumped over.
    assert calls == [t - 2.0, t - 1.75 + 0.5, t - 0.75 + 0.5]


def test_a_daily_sky_advances_past_every_sunrise_it_is_searched_from():
    """The guard's happy path: each result is strictly past the previous one."""
    moment = at(2024, 5, 10, 9, 0)
    t = jd(moment)
    rise_after, calls = counting_sky(*[t - 1.8 + n for n in range(4)])

    window = window_for(moment, rise_after)

    assert isinstance(window, SunriseWindow)
    assert window.previous_julian_day_ut == t - 0.8
    assert window.next_julian_day_ut == t + 0.2
    # Every value the sky returned was strictly greater than the one before.
    returned = [t - 1.8, t - 0.8, t + 0.2]
    assert returned == sorted(set(returned))
    assert len(calls) == 3


def test_a_sky_that_does_not_advance_is_a_visible_failure_not_a_hang():
    """A non-advancing event would otherwise spin the loop forever.

    ``RuntimeError`` and not ``AssertionError``: the difference between a
    visible error and a hang must survive ``python -O``, which strips asserts.
    The check is a check, not a clamp -- it refuses to continue with the value,
    it does not quietly push it along. Both ways of failing to advance are
    covered: returning the same sunrise again, and returning an earlier one.
    """
    moment = at(2024, 5, 10, 9, 0)
    t = jd(moment)

    def stuck(julian_day, latitude, longitude):
        return t - 1.0

    def backwards(julian_day, latitude, longitude):
        return t - 1.0 if julian_day <= t - 1.0 else t - 1.5

    with pytest.raises(RuntimeError, match="did not advance"):
        window_for(moment, stuck)

    with pytest.raises(RuntimeError, match="did not advance"):
        window_for(moment, backwards)


def test_a_sunrise_far_before_its_probe_is_refused():
    """The third check: an event from well behind the probe that asked for it.

    The library scans from two hours before its start time, so a result a
    little behind the probe is conceivable; a result a quarter of a day behind
    it is not, and would mean the accessor is answering a different question.
    The fake below advances -- the second value is after the first, so the
    progress check is satisfied -- and still lands far behind its probe.
    """
    moment = at(2024, 5, 10, 9, 0)
    t = jd(moment)
    answers = iter([t - 1.9, t - 1.8])

    def drifting(julian_day, latitude, longitude):
        return next(answers)

    with pytest.raises(RuntimeError, match="went backwards"):
        window_for(moment, drifting)


def test_an_advance_of_a_single_ulp_cannot_survive_the_backtrack_check():
    """The two checks together, and why the strict one is not enough alone.

    A sunrise one ULP past the previous one is a legitimate *advance*, so the
    progress check would let it through. But the probe that asked for it sits a
    half-day later, so such a value is half a day behind its probe and the
    backtrack check refuses it. That is the intended reading: consecutive
    sunrises are about a day apart, and anything that says otherwise is the
    library misbehaving rather than an unusually short day.
    """
    moment = at(2024, 5, 10, 9, 0)
    t = jd(moment)
    first = t - 1.0
    second = math.nextafter(first, math.inf)
    answers = iter([first, second, t + 0.5])

    def scripted(julian_day, latitude, longitude):
        return next(answers)

    assert second > first
    with pytest.raises(RuntimeError, match="went backwards"):
        window_for(moment, scripted)


def test_the_two_checks_report_the_two_different_failures():
    """A stuck sky fails the progress check; a drifting one the backtrack."""
    moment = at(2024, 5, 10, 9, 0)
    t = jd(moment)

    def stuck(julian_day, latitude, longitude):
        return t - 1.0

    drifting_answers = iter([t - 1.9, t - 1.8])

    def drifting(julian_day, latitude, longitude):
        return next(drifting_answers)

    with pytest.raises(RuntimeError, match="did not advance"):
        window_for(moment, stuck)
    with pytest.raises(RuntimeError, match="went backwards"):
        window_for(moment, drifting)


def test_a_sunrise_slightly_behind_its_probe_is_accepted():
    """Within the two-hour look-back is fine; ``MAX_BACKTRACK_DAYS`` has room."""
    moment = at(2024, 5, 10, 9, 0)
    t = jd(moment)
    answers = iter([t - 1.0, t - 0.55, t + 0.5])

    def scripted(julian_day, latitude, longitude):
        return next(answers)

    window = window_for(moment, scripted)

    # The second value came back 0.05 days behind the probe at t - 0.5, which
    # is inside the quarter-day tolerance and well outside a plausible skip.
    assert isinstance(window, SunriseWindow)
    assert window.previous_julian_day_ut == t - 0.55
    assert MAX_BACKTRACK_DAYS == 0.25
    assert 2.0 / 24.0 < MAX_BACKTRACK_DAYS < SEARCH_STEP_DAYS


def test_the_guard_does_not_fire_when_the_sky_simply_runs_out():
    """``rise is None`` is a refusal, not a failure to advance."""
    moment = at(2024, 5, 10, 9, 0)
    t = jd(moment)

    result = window_for(moment, sky(t - 1.0), latitude=80.0)

    assert isinstance(result, SunriseUnavailable)
    assert result.reason == REASON_NO_NEXT_SUNRISE


# --- the three refusals (decision D3) --------------------------------------


def test_no_sunrise_in_the_two_days_up_to_the_instant():
    moment = at(2024, 6, 21, 12, 0)
    t = jd(moment)
    result = window_for(moment, sky(t + 0.5), latitude=80.0)

    assert isinstance(result, SunriseUnavailable)
    assert result.reason == REASON_NO_PREVIOUS_SUNRISE
    assert result.latitude == 80.0
    assert result.convention == SUNRISE_CONVENTION


def test_no_sunrise_at_all():
    moment = at(2024, 6, 21, 12, 0)
    result = window_for(moment, sky(), latitude=80.0)

    assert isinstance(result, SunriseUnavailable)
    assert result.reason == REASON_NO_PREVIOUS_SUNRISE


def test_no_sunrise_after_the_previous_one():
    moment = at(2024, 6, 21, 12, 0)
    t = jd(moment)
    result = window_for(moment, sky(t - 1.0), latitude=80.0)

    assert isinstance(result, SunriseUnavailable)
    assert result.reason == REASON_NO_NEXT_SUNRISE


def test_two_sunrises_too_far_apart_are_not_a_vara_boundary():
    moment = at(2024, 6, 21, 12, 0)
    t = jd(moment)
    result = window_for(moment, sky(t - 0.25, t + 2.5), latitude=80.0)

    assert isinstance(result, SunriseUnavailable)
    assert result.reason == REASON_SUNRISES_NOT_CONSECUTIVE


def test_the_consecutive_gap_is_inclusive_at_exactly_two_days():
    """``> 2.0`` refuses; exactly two days is still accepted."""
    moment = at(2024, 6, 21, 12, 0)
    t = jd(moment)

    accepted = window_for(
        moment, sky(t - 0.5, t - 0.5 + MAX_CONSECUTIVE_GAP_DAYS), latitude=80.0
    )
    refused = window_for(
        moment,
        sky(
            t - 0.5,
            math.nextafter(t - 0.5 + MAX_CONSECUTIVE_GAP_DAYS, math.inf),
        ),
        latitude=80.0,
    )

    assert isinstance(accepted, SunriseWindow)
    assert isinstance(refused, SunriseUnavailable)
    assert refused.reason == REASON_SUNRISES_NOT_CONSECUTIVE


def test_the_three_reasons_are_distinct_and_enumerated():
    assert len(set(UNAVAILABLE_REASONS)) == 3
    assert REASON_NO_PREVIOUS_SUNRISE in UNAVAILABLE_REASONS
    assert REASON_NO_NEXT_SUNRISE in UNAVAILABLE_REASONS
    assert REASON_SUNRISES_NOT_CONSECUTIVE in UNAVAILABLE_REASONS


def test_the_refusal_records_the_window_it_searched():
    moment = at(2024, 6, 21, 12, 0)
    t = jd(moment)
    result = window_for(moment, sky(), latitude=80.0, longitude=25.0)

    assert result.searched_from_utc == datetime_from_julian_day(
        t - SEARCH_SPAN_DAYS
    )
    assert result.searched_to_utc == datetime_from_julian_day(t)
    assert result.searched_to_utc - result.searched_from_utc == timedelta(
        days=SEARCH_SPAN_DAYS
    )
    assert result.longitude == 25.0


def test_an_unavailable_sunrise_is_never_an_exception():
    """Decision D3: a polar instant is a result, not a failure."""
    moment = at(2024, 12, 21, 12, 0)
    result = window_for(moment, sky(), latitude=-80.0)

    assert isinstance(result, SunriseUnavailable)


# --- the window's own contents ---------------------------------------------


def test_the_window_carries_both_the_julian_days_and_the_datetimes():
    moment = at(2024, 5, 10, 9, 0)
    t = jd(moment)
    window = window_for(moment, sky(t - 0.5, t + 0.5))

    assert window.previous_julian_day_ut == t - 0.5
    assert window.next_julian_day_ut == t + 0.5
    assert window.previous_utc == datetime_from_julian_day(t - 0.5)
    assert window.next_utc == datetime_from_julian_day(t + 0.5)
    assert window.previous_utc.tzinfo is timezone.utc
    assert window.convention == SUNRISE_CONVENTION


def test_the_local_datetimes_are_the_utc_ones_in_the_places_zone():
    moment = at(2024, 5, 10, 9, 0)
    t = jd(moment)
    window = find_sunrise_window(
        moment, *SOMEWHERE, rise_after=sky(t - 0.5, t + 0.5)
    )

    assert window.previous_local == window.previous_utc
    assert window.previous_local.utcoffset() == timedelta(hours=5, minutes=30)
    assert window.next_local == window.next_utc
    assert window.next_local.utcoffset() == timedelta(hours=5, minutes=30)


def test_the_window_brackets_the_instant():
    moment = at(2024, 5, 10, 9, 0)
    t = jd(moment)
    window = window_for(moment, sky(t - 0.4, t + 0.6))

    assert window.previous_julian_day_ut <= t < window.next_julian_day_ut


# --- the vara the window names ---------------------------------------------


def sunrise_at(moment, zone_id, rise_after=None):
    """A window whose previous sunrise is exactly ``moment``."""
    t = jd(moment)
    later = jd(moment + timedelta(days=1))
    instant = moment + timedelta(hours=3)
    window = find_sunrise_window(
        instant, 0.0, 0.0, zone_id, rise_after=sky(t, later)
    )
    assert isinstance(window, SunriseWindow)
    return window


#: Seven consecutive civil dates, one per weekday, with the vara each names.
SEVEN_DAYS = (
    (date(2024, 5, 5), 0, "Ravivara", "Sunday", Graha.SUN),
    (date(2024, 5, 6), 1, "Somavara", "Monday", Graha.MOON),
    (date(2024, 5, 7), 2, "Mangalavara", "Tuesday", Graha.MARS),
    (date(2024, 5, 8), 3, "Budhavara", "Wednesday", Graha.MERCURY),
    (date(2024, 5, 9), 4, "Guruvara", "Thursday", Graha.JUPITER),
    (date(2024, 5, 10), 5, "Shukravara", "Friday", Graha.VENUS),
    (date(2024, 5, 11), 6, "Shanivara", "Saturday", Graha.SATURN),
)


@pytest.mark.parametrize(
    "civil_date,index,name,english,lord",
    SEVEN_DAYS,
    ids=[row[3] for row in SEVEN_DAYS],
)
def test_every_weekday_converts_to_its_vara(
    civil_date, index, name, english, lord
):
    """Python counts from Monday, the varas from Sunday; all seven are pinned."""
    sunrise = datetime(
        civil_date.year, civil_date.month, civil_date.day, 6, 0, tzinfo=IST
    )
    window = sunrise_at(sunrise, "Asia/Kolkata")
    vara = vara_from_sunrise(window)

    assert window.previous_local.date() == civil_date
    assert vara.index == index
    assert vara.number == index + 1
    assert vara.name == name
    assert vara.key == name.lower()
    assert vara.english_weekday == english
    assert vara.lord is lord


def test_the_vara_carries_the_window_it_was_read_from():
    """Specification 4.3: ``vara.sunrise is panchanga.sunrise``."""
    window = sunrise_at(datetime(2024, 5, 10, 6, 0, tzinfo=IST), "Asia/Kolkata")

    assert vara_from_sunrise(window).sunrise is window


# --- the local civil date is the whole point -------------------------------


def test_a_pre_dawn_birth_keeps_the_previous_days_vara():
    """The instant's own local date has rolled over; the vara has not.

    1995-03-21 04:30 IST is the small hours of a Tuesday, and its UTC date is
    still the Monday. The last sunrise before it was on Monday morning, so the
    vara is Somavara -- neither of the two dates the instant itself carries.
    """
    instant = datetime(1995, 3, 21, 4, 30, tzinfo=IST)
    previous = datetime(1995, 3, 20, 6, 30, tzinfo=IST)
    following = datetime(1995, 3, 21, 6, 30, tzinfo=IST)

    window = find_sunrise_window(
        instant,
        31.32556,
        75.57917,
        "Asia/Kolkata",
        rise_after=sky(jd(previous), jd(following)),
    )
    vara = vara_from_sunrise(window)

    assert instant.astimezone(timezone.utc).date() == date(1995, 3, 20)
    assert instant.date() == date(1995, 3, 21)
    assert window.previous_local.date() == date(1995, 3, 20)
    assert vara.name == "Somavara"
    assert vara.english_weekday == "Monday"


def test_a_sunrise_whose_utc_date_differs_from_its_local_date():
    """Asia/Kolkata at +05:30: an early sunrise is the previous UTC day."""
    sunrise = datetime(2024, 5, 10, 5, 0, tzinfo=IST)

    window = sunrise_at(sunrise, "Asia/Kolkata")

    assert window.previous_utc.date() == date(2024, 5, 9)
    assert window.previous_local.date() == date(2024, 5, 10)
    assert vara_from_sunrise(window).name == "Shukravara"


# --- daylight saving -------------------------------------------------------


def test_a_spring_forward_day_in_europe_london():
    """2024-03-31: the clocks go from +00:00 to +01:00 at 01:00 UTC."""
    before = datetime(2024, 3, 30, 5, 42, tzinfo=timezone.utc)
    after = datetime(2024, 3, 31, 5, 40, tzinfo=timezone.utc)

    saturday = sunrise_at(before, "Europe/London")
    sunday = sunrise_at(after, "Europe/London")

    assert saturday.previous_local.utcoffset() == timedelta(0)
    assert sunday.previous_local.utcoffset() == timedelta(hours=1)
    assert saturday.previous_local.date() == date(2024, 3, 30)
    assert sunday.previous_local.date() == date(2024, 3, 31)
    assert sunday.previous_local.hour == 6
    assert vara_from_sunrise(saturday).name == "Shanivara"
    assert vara_from_sunrise(sunday).name == "Ravivara"


def test_a_spring_forward_day_in_america_new_york():
    """2024-03-10: the clocks go from -05:00 to -04:00 at 07:00 UTC.

    The sunrise at 04:00 UTC is still 23:00 on the *ninth* in New York, so the
    vara is the Saturday's even though the UTC date says Sunday.
    """
    late_saturday = datetime(2024, 3, 10, 4, 0, tzinfo=timezone.utc)
    sunday_morning = datetime(2024, 3, 10, 11, 30, tzinfo=timezone.utc)

    earlier = sunrise_at(late_saturday, "America/New_York")
    later = sunrise_at(sunday_morning, "America/New_York")

    assert earlier.previous_utc.date() == date(2024, 3, 10)
    assert earlier.previous_local.date() == date(2024, 3, 9)
    assert earlier.previous_local.utcoffset() == timedelta(hours=-5)
    assert vara_from_sunrise(earlier).name == "Shanivara"

    assert later.previous_local.date() == date(2024, 3, 10)
    assert later.previous_local.utcoffset() == timedelta(hours=-4)
    assert later.previous_local.hour == 7
    assert vara_from_sunrise(later).name == "Ravivara"


def test_a_fall_back_day_in_america_new_york():
    """2024-11-03: the clocks go from -04:00 to -05:00 at 06:00 UTC."""
    before = datetime(2024, 11, 3, 3, 30, tzinfo=timezone.utc)
    after = datetime(2024, 11, 3, 11, 30, tzinfo=timezone.utc)

    earlier = sunrise_at(before, "America/New_York")
    later = sunrise_at(after, "America/New_York")

    assert earlier.previous_local.utcoffset() == timedelta(hours=-4)
    assert earlier.previous_local.date() == date(2024, 11, 2)
    assert vara_from_sunrise(earlier).name == "Shanivara"

    assert later.previous_local.utcoffset() == timedelta(hours=-5)
    assert later.previous_local.date() == date(2024, 11, 3)
    assert vara_from_sunrise(later).name == "Ravivara"


def test_the_dst_offset_is_read_at_the_sunrise_not_at_the_instant():
    """One window, two offsets: the pair straddles the transition.

    The previous sunrise is before the London spring-forward and the next one
    after it, so the two local datetimes carry different offsets even though
    they came from the same window and the same zone.
    """
    previous = datetime(2024, 3, 30, 5, 42, tzinfo=timezone.utc)
    following = datetime(2024, 3, 31, 5, 40, tzinfo=timezone.utc)
    instant = datetime(2024, 3, 31, 0, 30, tzinfo=timezone.utc)

    window = find_sunrise_window(
        instant,
        51.5,
        -0.1,
        "Europe/London",
        rise_after=sky(jd(previous), jd(following)),
    )

    assert window.previous_local.utcoffset() == timedelta(0)
    assert window.next_local.utcoffset() == timedelta(hours=1)
    assert vara_from_sunrise(window).name == "Shanivara"


# --- the date line ---------------------------------------------------------


def test_a_date_line_zone_names_tomorrows_civil_date():
    """Pacific/Kiritimati is +14:00: 16:30 UTC is 06:30 the next morning."""
    sunrise = datetime(2024, 6, 15, 16, 30, tzinfo=timezone.utc)

    window = sunrise_at(sunrise, "Pacific/Kiritimati")
    vara = vara_from_sunrise(window)

    assert window.previous_utc.date() == date(2024, 6, 15)
    assert window.previous_local.utcoffset() == timedelta(hours=14)
    assert window.previous_local.date() == date(2024, 6, 16)
    assert window.previous_local.hour == 6
    assert date(2024, 6, 15).weekday() == 5      # a Saturday in UTC
    assert date(2024, 6, 16).weekday() == 6      # a Sunday on Kiritimati
    assert vara.name == "Ravivara"
    assert vara.english_weekday == "Sunday"


# --- input validation ------------------------------------------------------


def test_a_naive_instant_is_refused():
    with pytest.raises(ValueError):
        find_sunrise_window(
            datetime(2024, 5, 10, 9, 0), 0.0, 0.0, "UTC", rise_after=sky()
        )


def test_an_unknown_timezone_is_refused():
    moment = at(2024, 5, 10, 9, 0)

    with pytest.raises(InvalidTimezoneError):
        find_sunrise_window(
            moment, 0.0, 0.0, "Mars/Olympus_Mons", rise_after=sky(jd(moment))
        )
    with pytest.raises(InvalidTimezoneError):
        find_sunrise_window(
            moment, 0.0, 0.0, "+05:30", rise_after=sky(jd(moment))
        )
    with pytest.raises(InvalidTimezoneError):
        find_sunrise_window(moment, 0.0, 0.0, None, rise_after=sky(jd(moment)))


@pytest.mark.parametrize(
    "latitude,longitude",
    (
        (90.5, 0.0),
        (-90.5, 0.0),
        (0.0, 180.5),
        (0.0, -180.5),
        (float("nan"), 0.0),
        (float("inf"), 0.0),
        (0.0, float("nan")),
        ("31.3", 0.0),
        (0.0, None),
        (True, 0.0),
    ),
)
def test_coordinates_off_the_globe_are_refused(latitude, longitude):
    moment = at(2024, 5, 10, 9, 0)

    with pytest.raises(ValueError):
        find_sunrise_window(
            moment, latitude, longitude, "UTC", rise_after=sky(jd(moment))
        )


@pytest.mark.parametrize(
    "latitude,longitude",
    ((90.0, 180.0), (-90.0, -180.0), (0.0, 0.0), (31.32556, 75.57917)),
)
def test_the_extremes_of_the_globe_are_accepted(latitude, longitude):
    moment = at(2024, 5, 10, 9, 0)
    t = jd(moment)

    window = find_sunrise_window(
        moment, latitude, longitude, "UTC", rise_after=sky(t - 0.5, t + 0.5)
    )

    assert isinstance(window, SunriseWindow)


def test_the_validation_happens_before_the_sky_is_asked():
    """An unusable input costs no ephemeris call."""
    rise_after, calls = counting_sky(0.0)

    with pytest.raises(ValueError):
        find_sunrise_window(
            datetime(2024, 5, 10, 9, 0), 0.0, 0.0, "UTC", rise_after=rise_after
        )
    with pytest.raises(ValueError):
        find_sunrise_window(
            at(2024, 5, 10, 9, 0), 91.0, 0.0, "UTC", rise_after=rise_after
        )
    with pytest.raises(InvalidTimezoneError):
        find_sunrise_window(
            at(2024, 5, 10, 9, 0), 0.0, 0.0, "Nowhere/Nowhere",
            rise_after=rise_after,
        )

    assert calls == []


# --- the default sky is the Layer 5 accessor -------------------------------


def test_the_default_rise_after_is_the_layer_five_accessor():
    """Not a copy of it: the same function, reached through the boundary."""
    import inspect

    from vedic_chart.ephemeris.swiss_ephemeris import calc_sunrise_hindu

    source = inspect.getsource(default_rise_after)

    assert "calc_sunrise_hindu(" in source
    assert calc_sunrise_hindu.__module__ == (
        "vedic_chart.ephemeris.swiss_ephemeris"
    )

    signature = inspect.signature(find_sunrise_window)
    assert signature.parameters["rise_after"].default is default_rise_after
    assert signature.parameters["rise_after"].kind is (
        inspect.Parameter.KEYWORD_ONLY
    )


# --- the Julian Day conversion ---------------------------------------------


def test_the_julian_day_conversion_round_trips_through_the_unix_epoch():
    for moment in (
        at(1970, 1, 1),
        at(1995, 3, 21, 1, 5, 11),
        at(2024, 5, 10, 9, 0),
        at(2100, 12, 31, 23, 59, 59),
    ):
        converted = datetime_from_julian_day(julian_day_ut(moment))
        assert abs(converted - moment) < timedelta(milliseconds=1)
        assert converted.tzinfo is timezone.utc


def test_the_zone_resolver_returns_a_usable_zone():
    zone = resolve_zone("Asia/Kolkata")

    assert at(2024, 5, 10, 9, 0).astimezone(zone).utcoffset() == timedelta(
        hours=5, minutes=30
    )


# --- immutability ----------------------------------------------------------


def test_the_sunrise_result_types_are_frozen():
    moment = at(2024, 5, 10, 9, 0)
    t = jd(moment)
    window = window_for(moment, sky(t - 0.5, t + 0.5))
    unavailable = window_for(moment, sky(), latitude=80.0)
    vara = vara_from_sunrise(window)

    assert isinstance(window, SunriseWindow)
    assert isinstance(unavailable, SunriseUnavailable)
    assert isinstance(vara, Vara)

    with pytest.raises(dataclasses.FrozenInstanceError):
        window.previous_julian_day_ut = 0.0
    with pytest.raises(dataclasses.FrozenInstanceError):
        unavailable.reason = "tampered"
    with pytest.raises(dataclasses.FrozenInstanceError):
        vara.name = "tampered"


# --- normalisation of the instant (specification 2.4) ----------------------


def test_any_aware_spelling_of_the_instant_gives_the_same_window():
    """+00:00, a fixed +05:30 and a ZoneInfo are one instant, not three."""
    utc = at(2024, 5, 10, 9, 0)
    t = jd(utc)
    spellings = (
        utc,
        utc.astimezone(IST),
        utc.astimezone(ZoneInfo("Asia/Kolkata")),
        utc.astimezone(ZoneInfo("America/New_York")),
    )

    windows = [
        find_sunrise_window(
            spelling, 0.0, 0.0, "UTC", rise_after=sky(t - 0.5, t + 0.5)
        )
        for spelling in spellings
    ]

    assert all(window == windows[0] for window in windows)
    assert windows[0].previous_julian_day_ut == t - 0.5


def test_the_normalisation_helper_keeps_the_instant_and_moves_the_tzinfo():
    utc = at(2024, 5, 10, 9, 0)

    for spelling in (utc, utc.astimezone(IST), utc.astimezone(ZoneInfo("UTC"))):
        normalised, julian_day = utc_instant(spelling)

        assert normalised == spelling
        assert normalised.tzinfo is timezone.utc
        assert julian_day == jd(utc)


def test_the_normalisation_helper_refuses_a_naive_datetime():
    """``astimezone`` would silently assume the machine's zone; Layer 4 refuses."""
    with pytest.raises(ValueError):
        utc_instant(datetime(2024, 5, 10, 9, 0))


# --- the real sky, where a None has to mean what the library means ---------

#: Tromso: far enough north for the library's slow method and its 28-hour
#: window, and the case that showed v0.1's bracketing to be wrong.
TROMSO = (69.65, 18.96, "Europe/Oslo")


@pytest.fixture(scope="module")
def ephemeris():
    with ephemeris_session(EPHE_DIR):
        yield


def test_the_tromso_regression(ephemeris):
    """2026-01-19 15:00 UTC at 69.65 N: available, and v0.1 said it was not.

    The Sun rose at 10:35:38 UTC that morning -- the first geometric-centre
    sunrise of the year there -- and again at 10:15:37 UTC on the 20th. The
    probes two days and thirty-six hours earlier both return None, which v0.1
    read as "no sunrise in the span".
    """
    moment = at(2026, 1, 19, 15, 0)
    window = find_sunrise_window(moment, *TROMSO)

    assert isinstance(window, SunriseWindow)

    assert abs(
        window.previous_utc - at(2026, 1, 19, 10, 35, 38)
    ) <= timedelta(seconds=1)
    assert abs(
        window.next_utc - at(2026, 1, 20, 10, 15, 37)
    ) <= timedelta(seconds=1)

    assert window.previous_julian_day_ut <= jd(moment)
    assert window.next_julian_day_ut > jd(moment)

    local = window.previous_local
    assert local.utcoffset() == timedelta(hours=1)
    assert local.date() == date(2026, 1, 19)
    assert (local.hour, local.minute, local.second) == (11, 35, 38)

    vara = vara_from_sunrise(window)
    assert vara.name == "Somavara"
    assert vara.english_weekday == "Monday"
    assert vara.lord is Graha.MOON


def test_the_tromso_regression_needed_more_than_the_first_probe(ephemeris):
    """The Nones that fooled v0.1 are still Nones; the walk just carries on."""
    moment = at(2026, 1, 19, 15, 0)
    t = jd(moment)
    rise_after, calls = counting_calls(default_rise_after)

    window = find_sunrise_window(moment, *TROMSO, rise_after=rise_after)

    assert default_rise_after(t - 2.0, 69.65, 18.96) is None
    assert default_rise_after(t - 1.5, 69.65, 18.96) is None
    assert default_rise_after(t - 1.0, 69.65, 18.96) is not None
    assert calls[:3] == [t - 2.0, t - 1.5, t - 1.0]
    assert len(calls) <= MAX_PROBES
    assert isinstance(window, SunriseWindow)


@pytest.mark.parametrize(
    "moment,latitude,longitude",
    (
        (at(2026, 1, 18, 12, 0), 69.65, 18.96),
        (at(2026, 12, 1, 12, 0), 69.65, 18.96),
        (at(2024, 6, 21, 12, 0), 80.0, 0.0),
        (at(2024, 12, 21, 12, 0), 80.0, 0.0),
    ),
    ids=("tromso_before_first_sunrise", "tromso_polar_night",
         "eighty_north_june", "eighty_north_december"),
)
def test_genuinely_unavailable_days_are_still_unavailable(
    ephemeris, moment, latitude, longitude
):
    """The fix must not turn a real polar night into an invented sunrise.

    Tromso on 2026-01-18 is the sharp case: the Sun rises the *next* morning,
    so every probe at or before the instant is silent while probes after it are
    not. The reason is the no-previous one, because that is what is true.
    """
    result = find_sunrise_window(moment, latitude, longitude, "UTC")

    assert isinstance(result, SunriseUnavailable)
    assert result.reason == REASON_NO_PREVIOUS_SUNRISE
    assert result.latitude == latitude


def test_the_day_before_tromso_s_first_sunrise_has_one_the_day_after(
    ephemeris,
):
    """Not silence everywhere -- silence only where it should be."""
    moment = at(2026, 1, 18, 12, 0)
    t = jd(moment)

    assert default_rise_after(t - 2.0, 69.65, 18.96) is None
    assert default_rise_after(t - 0.5, 69.65, 18.96) is None
    assert default_rise_after(t, 69.65, 18.96) > t
