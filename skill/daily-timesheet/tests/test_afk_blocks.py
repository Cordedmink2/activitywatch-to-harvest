"""Tests for the day-shape arithmetic in afk_blocks.py.

These are the numbers the skill bills against: where the day ended, which gaps
are real breaks, and which active time a proposed set of blocks leaves unbilled.
Getting any of them wrong writes a wrong timesheet, so they get tested against
hand-built event streams rather than whatever ActivityWatch happens to hold.
"""

import datetime as dt
import os
import sys

import pytest

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts")
sys.path.insert(0, SCRIPTS)
import afk_blocks as ab

DAY = dt.date(2026, 5, 28)


def ev(hhmm, minutes, status):
    """One AW afk event: starts at UTC hh:mm on DAY, runs `minutes` long."""
    h, m = hhmm.split(":")
    return {
        "timestamp": f"{DAY.isoformat()}T{h}:{m}:00+00:00",
        "duration": minutes * 60,
        "data": {"status": status},
    }


def at(hhmm):
    h, m = (int(x) for x in hhmm.split(":"))
    return dt.datetime.combine(DAY, dt.time(h, m), tzinfo=dt.timezone.utc)


def hhmm(d):
    return d.strftime("%H:%M")


def test_dedupe_heartbeats_keeps_the_longest_duration_per_timestamp():
    """AW re-emits an ongoing event at the same timestamp with a growing duration."""
    events = [ev("09:00", 5, "not-afk"), ev("09:00", 40, "not-afk"), ev("09:00", 20, "not-afk")]
    kept = ab.dedupe_heartbeats(events)
    assert len(kept) == 1
    assert kept[0]["duration"] == 40 * 60


def test_to_spans_gives_start_end_status_and_duration():
    spans = ab.to_spans([ev("09:00", 30, "not-afk")])
    start, end, status, dur = spans[0]
    assert (hhmm(start), hhmm(end), status, dur) == ("09:00", "09:30", "not-afk", 1800)


def test_work_bounds_runs_first_to_last_not_afk():
    spans = ab.to_spans([
        ev("08:00", 60, "afk"),        # not at work yet
        ev("09:00", 90, "not-afk"),
        ev("10:30", 30, "afk"),
        ev("11:00", 60, "not-afk"),
        ev("12:00", 300, "afk"),       # done for the day
    ])
    bounds = ab.work_bounds(spans)
    assert (hhmm(bounds["work_start"]), hhmm(bounds["work_end"])) == ("09:00", "12:00")
    assert bounds["blip"] is False


def test_work_bounds_flags_a_late_flicker_as_a_blip():
    """A one-minute mouse nudge hours after real work must not stretch the day."""
    spans = ab.to_spans([
        ev("09:00", 120, "not-afk"),
        ev("11:00", 180, "afk"),
        ev("14:00", 1, "not-afk"),     # the flicker
    ])
    bounds = ab.work_bounds(spans)
    assert bounds["blip"] is True
    assert hhmm(bounds["work_end"]) == "14:01"
    assert hhmm(bounds["last_solid_end"]) == "11:00"


def test_work_bounds_returns_none_for_a_day_with_no_activity():
    assert ab.work_bounds(ab.to_spans([ev("09:00", 480, "afk")])) is None


def test_find_breaks_ignores_afk_outside_the_workday():
    """The long afk before the first and after the last activity isn't a break."""
    spans = ab.to_spans([
        ev("06:00", 180, "afk"),       # before work
        ev("09:00", 60, "not-afk"),
        ev("10:00", 30, "afk"),        # a real break
        ev("10:30", 60, "not-afk"),
        ev("11:30", 300, "afk"),       # after work
    ])
    bounds = ab.work_bounds(spans)
    breaks = ab.find_breaks(spans, bounds["work_start"], bounds["work_end"], ab.DEFAULT_THRESHOLD)
    assert [(hhmm(s), hhmm(e)) for s, e, _ in breaks] == [("10:00", "10:30")]


def test_find_breaks_ignores_afk_shorter_than_the_threshold():
    spans = ab.to_spans([
        ev("09:00", 60, "not-afk"),
        ev("10:00", 10, "afk"),        # 10 min < 17.5 min threshold
        ev("10:10", 60, "not-afk"),
    ])
    bounds = ab.work_bounds(spans)
    assert ab.find_breaks(spans, bounds["work_start"], bounds["work_end"], ab.DEFAULT_THRESHOLD) == []


def test_active_spans_folds_short_afk_in_and_splits_on_a_real_break():
    spans = ab.to_spans([
        ev("09:00", 60, "not-afk"),
        ev("10:00", 5, "afk"),         # short: folded in
        ev("10:05", 55, "not-afk"),
        ev("11:00", 40, "afk"),        # real break: splits
        ev("11:40", 60, "not-afk"),
    ])
    assert [(hhmm(s), hhmm(e)) for s, e in ab.active_spans(spans, ab.DEFAULT_THRESHOLD)] == [
        ("09:00", "11:00"), ("11:40", "12:40"),
    ]


def test_active_seconds_clips_to_the_requested_window():
    spans = ab.to_spans([ev("09:00", 60, "not-afk"), ev("10:30", 60, "not-afk")])
    # 09:30-11:00 catches the tail of the first span (30 min) and half the second (30 min).
    assert ab.active_seconds(spans, at("09:30"), at("11:00")) == 60 * 60


def test_active_seconds_ignores_afk_time():
    spans = ab.to_spans([ev("09:00", 60, "afk")])
    assert ab.active_seconds(spans, at("09:00"), at("10:00")) == 0


def test_uncovered_segments_reports_active_time_the_proposed_blocks_miss():
    """The under-billing guard: an hour of real work left out of the blocks."""
    spans = ab.to_spans([ev("09:00", 180, "not-afk")])          # 09:00-12:00 active
    active = ab.active_spans(spans, ab.DEFAULT_THRESHOLD)
    proposed = [(at("09:00"), at("11:00"))]                     # 11:00-12:00 unbilled
    gaps = ab.uncovered_segments(spans, active, proposed)
    assert [(hhmm(s), hhmm(e)) for s, e, _ in gaps] == [("11:00", "12:00")]
    assert gaps[0][2] == 60 * 60


def test_uncovered_segments_ignores_slivers_under_fifteen_minutes():
    """Rounding a block to the nearest quarter hour shouldn't raise a flag."""
    spans = ab.to_spans([ev("09:00", 130, "not-afk")])          # 09:00-11:10
    active = ab.active_spans(spans, ab.DEFAULT_THRESHOLD)
    proposed = [(at("09:00"), at("11:00"))]                     # 10 min left over
    assert ab.uncovered_segments(spans, active, proposed) == []


def test_uncovered_segments_is_empty_when_the_blocks_cover_everything():
    spans = ab.to_spans([ev("09:00", 60, "not-afk"), ev("11:00", 60, "not-afk")])
    active = ab.active_spans(spans, ab.DEFAULT_THRESHOLD)
    proposed = [(at("09:00"), at("10:00")), (at("11:00"), at("12:00"))]
    assert ab.uncovered_segments(spans, active, proposed) == []


def test_parse_range_rejects_a_reversed_range():
    with pytest.raises(ValueError):
        ab.parse_range("17:00-09:00", DAY, dt.timedelta(hours=12))


def test_parse_range_converts_local_times_to_utc():
    start, end = ab.parse_range("09:00-17:00", DAY, dt.timedelta(hours=12))
    assert hhmm(start) == "21:00"          # 09:00 NZST the previous UTC day
    assert start.date() == dt.date(2026, 5, 27)
    assert (end - start) == dt.timedelta(hours=8)
