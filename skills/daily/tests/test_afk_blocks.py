"""Tests for the day-shape arithmetic in afk_blocks.py.

These are the numbers the skill bills against: where the day ended, which gaps
are real breaks, and which active time a proposed set of blocks leaves unbilled.
Getting any of them wrong writes a wrong timesheet, so they get tested against
hand-built event streams rather than whatever ActivityWatch happens to hold.
"""

import datetime as dt
import os
import sys
from zoneinfo import ZoneInfo

import pytest

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts")
sys.path.insert(0, SCRIPTS)
import afk_blocks as ab
from support import day, fixed

DAY = dt.date(2026, 5, 28)
D = day(offset=0)


def hhmm(d):
    return d.strftime("%H:%M")


def test_dedupe_heartbeats_keeps_the_longest_duration_per_timestamp():
    """AW re-emits an ongoing event at the same timestamp with a growing duration."""
    events = [D.event("09:00", minutes=5, status="not-afk"),
              D.event("09:00", minutes=40, status="not-afk"),
              D.event("09:00", minutes=20, status="not-afk")]
    kept = ab.dedupe_heartbeats(events)
    assert len(kept) == 1
    assert kept[0]["duration"] == 40 * 60


def test_to_spans_gives_start_end_status_and_duration():
    spans = ab.to_spans([D.event("09:00", minutes=30, status="not-afk")])
    start, end, status, dur = spans[0]
    assert (hhmm(start), hhmm(end), status, dur) == ("09:00", "09:30", "not-afk", 1800)


def test_work_bounds_runs_first_to_last_not_afk():
    spans = ab.to_spans([
        D.event("08:00", minutes=60, status="afk"),        # not at work yet
        D.event("09:00", minutes=90, status="not-afk"),
        D.event("10:30", minutes=30, status="afk"),
        D.event("11:00", minutes=60, status="not-afk"),
        D.event("12:00", minutes=300, status="afk"),       # done for the day
    ])
    bounds = ab.work_bounds(spans)
    assert bounds is not None
    assert (hhmm(bounds["work_start"]), hhmm(bounds["work_end"])) == ("09:00", "12:00")
    assert bounds["blip"] is False


def test_work_bounds_flags_a_late_flicker_as_a_blip():
    """A one-minute mouse nudge hours after real work must not stretch the day."""
    spans = ab.to_spans([
        D.event("09:00", minutes=120, status="not-afk"),
        D.event("11:00", minutes=180, status="afk"),
        D.event("14:00", minutes=1, status="not-afk"),     # the flicker
    ])
    bounds = ab.work_bounds(spans)
    assert bounds is not None
    assert bounds["blip"] is True
    assert hhmm(bounds["work_end"]) == "14:01"
    assert hhmm(bounds["last_solid_end"]) == "11:00"


def test_work_bounds_returns_none_for_a_day_with_no_activity():
    assert ab.work_bounds(ab.to_spans([D.event("09:00", minutes=480, status="afk")])) is None


def test_work_bounds_reports_only_bounds():
    """The whole-day activity total is not a bound - it belongs to its own function,
    where it gets tested rather than riding along untested inside this struct."""
    bounds = ab.work_bounds(ab.to_spans([D.event("09:00", minutes=60, status="not-afk")]))
    assert bounds is not None
    assert set(bounds) == {"work_start", "work_end", "last_solid_end", "blip"}


def test_total_active_seconds_sums_only_not_afk_time():
    spans = ab.to_spans([D.event("09:00", minutes=60, status="not-afk"),
                         D.event("10:00", minutes=30, status="afk"),
                         D.event("10:30", minutes=45, status="not-afk")])
    assert ab.total_active_seconds(spans) == (60 + 45) * 60


def test_find_breaks_ignores_afk_outside_the_workday():
    """The long afk before the first and after the last activity isn't a break."""
    spans = ab.to_spans([
        D.event("06:00", minutes=180, status="afk"),       # before work
        D.event("09:00", minutes=60, status="not-afk"),
        D.event("10:00", minutes=30, status="afk"),        # a real break
        D.event("10:30", minutes=60, status="not-afk"),
        D.event("11:30", minutes=300, status="afk"),       # after work
    ])
    bounds = ab.work_bounds(spans)
    assert bounds is not None
    breaks = ab.find_breaks(spans, bounds["work_start"], bounds["work_end"], ab.DEFAULT_THRESHOLD)
    assert [(hhmm(s), hhmm(e)) for s, e, _ in breaks] == [("10:00", "10:30")]


def test_find_breaks_ignores_afk_shorter_than_the_threshold():
    spans = ab.to_spans([
        D.event("09:00", minutes=60, status="not-afk"),
        D.event("10:00", minutes=10, status="afk"),        # 10 min < 17.5 min threshold
        D.event("10:10", minutes=60, status="not-afk"),
    ])
    bounds = ab.work_bounds(spans)
    assert bounds is not None
    assert ab.find_breaks(spans, bounds["work_start"], bounds["work_end"], ab.DEFAULT_THRESHOLD) == []


def test_active_spans_folds_short_afk_in_and_splits_on_a_real_break():
    spans = ab.to_spans([
        D.event("09:00", minutes=60, status="not-afk"),
        D.event("10:00", minutes=5, status="afk"),         # short: folded in
        D.event("10:05", minutes=55, status="not-afk"),
        D.event("11:00", minutes=40, status="afk"),        # real break: splits
        D.event("11:40", minutes=60, status="not-afk"),
    ])
    assert [(hhmm(s), hhmm(e)) for s, e in ab.active_spans(spans, ab.DEFAULT_THRESHOLD)] == [
        ("09:00", "11:00"), ("11:40", "12:40"),
    ]


def test_active_seconds_clips_to_the_requested_window():
    spans = ab.to_spans([D.event("09:00", minutes=60, status="not-afk"),
                         D.event("10:30", minutes=60, status="not-afk")])
    # 09:30-11:00 catches the tail of the first span (30 min) and half the second (30 min).
    assert ab.active_seconds(spans, D.at("09:30"), D.at("11:00")) == 60 * 60


def test_active_seconds_ignores_afk_time():
    spans = ab.to_spans([D.event("09:00", minutes=60, status="afk")])
    assert ab.active_seconds(spans, D.at("09:00"), D.at("10:00")) == 0


def test_uncovered_segments_reports_active_time_the_proposed_blocks_miss():
    """The under-billing guard: an hour of real work left out of the blocks."""
    spans = ab.to_spans([D.event("09:00", minutes=180, status="not-afk")])  # 09:00-12:00 active
    active = ab.active_spans(spans, ab.DEFAULT_THRESHOLD)
    proposed = [(D.at("09:00"), D.at("11:00"))]                     # 11:00-12:00 unbilled
    gaps = ab.uncovered_segments(spans, active, proposed)
    assert [(hhmm(s), hhmm(e)) for s, e, _ in gaps] == [("11:00", "12:00")]
    assert gaps[0][2] == 60 * 60


def test_uncovered_segments_ignores_slivers_under_fifteen_minutes():
    """Rounding a block to the nearest quarter hour shouldn't raise a flag."""
    spans = ab.to_spans([D.event("09:00", minutes=130, status="not-afk")])          # 09:00-11:10
    active = ab.active_spans(spans, ab.DEFAULT_THRESHOLD)
    proposed = [(D.at("09:00"), D.at("11:00"))]                     # 10 min left over
    assert ab.uncovered_segments(spans, active, proposed) == []


def test_uncovered_segments_is_empty_when_the_blocks_cover_everything():
    spans = ab.to_spans([D.event("09:00", minutes=60, status="not-afk"),
                         D.event("11:00", minutes=60, status="not-afk")])
    active = ab.active_spans(spans, ab.DEFAULT_THRESHOLD)
    proposed = [(D.at("09:00"), D.at("10:00")), (D.at("11:00"), D.at("12:00"))]
    assert ab.uncovered_segments(spans, active, proposed) == []


def test_parse_range_rejects_a_reversed_range():
    with pytest.raises(ValueError):
        ab.parse_range("17:00-09:00", DAY, fixed(12))


NZ_ZONE = ZoneInfo("Pacific/Auckland")
FALL_BACK = dt.date(2026, 4, 5)      # clocks go back at 03:00: 02:00-03:00 happens twice
SPRING_FORWARD = dt.date(2026, 9, 27)  # clocks go forward at 02:00: that hour never happens


def test_parse_range_takes_the_first_pass_over_a_repeated_hour():
    """02:30 happens twice on the fall-back day, so which one a `--window` names is a
    convention rather than a fact. It is the first — the pre-change one, at UTC+13.

    Pinned because three documents state it (`to_utc`'s docstring, `activitywatch.md`
    §"Time zones", `TESTING.md`) and nothing else measures it: the transition scenario
    deliberately avoids this hour, so a change to `fold` semantics would flip the answer
    with the whole suite still green.
    """
    start, _ = ab.parse_range("02:30-04:00", FALL_BACK, NZ_ZONE)
    assert start == dt.datetime(2026, 4, 4, 13, 30, tzinfo=dt.timezone.utc)


def test_a_window_over_the_repeated_hour_is_two_hours_long():
    """The consequence of the rule above, and the one that surprises: `02:00-03:00` on the
    fall-back day is an hour on the clock and two hours in real time, because the clock
    passes 02:00 twice. `active_ratio` divides by the elapsed figure, so a window written
    across that hour is measured against 120 minutes and reads about half what an hour of
    solid work would. Correct, and worth failing loudly if it ever silently became 60."""
    start, end = ab.parse_range("02:00-03:00", FALL_BACK, NZ_ZONE)
    assert (end - start) == dt.timedelta(hours=2)


def test_parse_range_says_so_when_a_range_falls_in_the_hour_the_clocks_skip():
    """`02:00-03:00` on a spring-forward day is ordered on the clock and empty in real
    time — 02:00 never happened. It reaches the same `end must be after start` guard as a
    reversed range, and that message would send a user hunting a typo they did not make.
    """
    with pytest.raises(ValueError) as exc:
        ab.parse_range("02:00-03:00", SPRING_FORWARD, NZ_ZONE)
    assert "skip" in str(exc.value)
    assert "after start" not in str(exc.value)


def test_parse_range_converts_local_times_to_utc():
    start, end = ab.parse_range("09:00-17:00", DAY, fixed(12))
    assert hhmm(start) == "21:00"          # 09:00 NZST the previous UTC day
    assert start.date() == dt.date(2026, 5, 27)
    assert (end - start) == dt.timedelta(hours=8)


# --- data holes: the watcher stops writing while the machine sleeps or is locked -------


def test_data_hole_with_no_events_is_reported_as_a_break():
    """A long absence leaves a HOLE in the event stream, not an `afk` event, so
    find_breaks() cannot see it. Real 2026-08-18 day: a 47-min lunch produced no event
    at all and the skeleton reported `breaks: (none)`."""
    spans = ab.insert_data_gaps(ab.to_spans([
        D.event("09:00", minutes=120, status="not-afk"),   # 09:00-11:00
        # watcher stops entirely: no events at all 11:00-12:00
        D.event("12:00", minutes=60, status="not-afk"),    # 12:00-13:00
    ]), ab.DEFAULT_THRESHOLD)
    breaks = ab.find_breaks(spans, D.at("09:00"), D.at("13:00"), ab.DEFAULT_THRESHOLD)
    assert [(hhmm(s), hhmm(e)) for s, e, _ in breaks] == [("11:00", "12:00")]


def test_data_hole_splits_the_active_span_rather_than_merging_across_it():
    """Without this the two work runs merge into one 09:00-13:00 span and the day reads
    as four unbroken hours of activity."""
    spans = ab.insert_data_gaps(ab.to_spans([
        D.event("09:00", minutes=120, status="not-afk"),
        D.event("12:00", minutes=60, status="not-afk"),
    ]), ab.DEFAULT_THRESHOLD)
    got = ab.active_spans(spans, ab.DEFAULT_THRESHOLD)
    assert [(hhmm(s), hhmm(e)) for s, e in got] == [("09:00", "11:00"), ("12:00", "13:00")]


def test_short_data_hole_is_not_a_break():
    """A brief hole is the watcher's own cadence, not an absence - fold it in."""
    spans = ab.insert_data_gaps(ab.to_spans([
        D.event("09:00", minutes=120, status="not-afk"),
        D.event("11:05", minutes=55, status="not-afk"),    # 5-min hole, well under threshold
    ]), ab.DEFAULT_THRESHOLD)
    assert ab.find_breaks(spans, D.at("09:00"), D.at("12:00"), ab.DEFAULT_THRESHOLD) == []
    assert len(ab.active_spans(spans, ab.DEFAULT_THRESHOLD)) == 1


def test_a_break_from_a_data_hole_is_distinguishable_from_a_recorded_afk_break():
    """Both are breaks, but only a recorded afk proves the user was at the desk and idle.
    A watcher outage must not be presented as an observed break."""
    spans = ab.insert_data_gaps(ab.to_spans([
        D.event("09:00", minutes=60, status="not-afk"),
        D.event("10:00", minutes=30, status="afk"),        # recorded: user idle at the desk
        D.event("10:30", minutes=30, status="not-afk"),
        # hole 11:00-12:00: watcher stopped entirely
        D.event("12:00", minutes=60, status="not-afk"),
    ]), ab.DEFAULT_THRESHOLD)
    kinds = {(hhmm(s), hhmm(e)): ab.break_kind(spans, s, e)
             for s, e, _ in ab.find_breaks(
                 spans, D.at("09:00"), D.at("13:00"), ab.DEFAULT_THRESHOLD)}
    assert kinds == {("10:00", "10:30"): "afk", ("11:00", "12:00"): "gap"}
