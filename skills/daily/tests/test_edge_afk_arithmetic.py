"""Edge arithmetic in afk_blocks.py: the exact seconds where the answer flips.

`test_afk_blocks.py` covers these functions in the middle of their range, where a
30-minute afk is obviously a break and an hour of unbilled work is obviously a miss.
This module covers the boundaries, because every constant in the script is one side
of a `>=` and the timesheet is written from whichever side the day happens to land
on. A 17.5-minute coffee break that reads as work, a two-hour idle evening that gets
billed because the flicker guard missed by a second, a quarter hour of real work that
drops out of the coverage report — those are the failures at stake here.

Everything is a direct call on hand-built spans. Whole-day behaviour lives in
`test_scenarios.py`; nothing here goes through `main()`, because every edge below is
reachable at the function level and a CLI round-trip would only re-test the plumbing.

Second-resolution timestamps throughout, so the helpers take seconds where the ones in
`test_afk_blocks.py` take minutes: a boundary that only exists at 1049-vs-1050 seconds
cannot be written in whole minutes.
"""

import datetime as dt

import afk_blocks as ab

DAY = dt.date(2026, 5, 28)
MIDNIGHT = dt.datetime.combine(DAY, dt.time(0, 0), tzinfo=dt.timezone.utc)


def at(clock):
    """`'HH:MM'` or `'HH:MM:SS'` on DAY, as UTC. Hours past 24 roll into the next day."""
    parts = [int(p) for p in clock.split(":")]
    while len(parts) < 3:
        parts.append(0)
    h, m, s = parts
    return MIDNIGHT + dt.timedelta(hours=h, minutes=m, seconds=s)


def ev(clock, seconds, status):
    """One AW afk event: starts at `clock` UTC on DAY, runs `seconds` long."""
    return {"timestamp": at(clock).isoformat(), "duration": seconds, "data": {"status": status}}


def spans(*events):
    return ab.to_spans(list(events))


def hms(d):
    return d.strftime("%H:%M:%S")


def pairs(sp):
    return [(hms(s), hms(e)) for s, e in sp]


# --------------------------------------------------------------------------------------
# Threshold boundaries — one second either side of every constant in the script
# --------------------------------------------------------------------------------------

def test_an_afk_run_of_exactly_the_threshold_is_a_break_and_one_second_less_is_not():
    """1050s is where "stepped out" starts. One second under and a 17.5-minute coffee
    break stays folded into the surrounding block and gets billed as work; one second
    over on the other side and a genuine stretch of desk time gets deducted."""
    def breaks_for(afk_seconds):
        sp = spans(ev("09:00", 3600, "not-afk"),
                   ev("10:00", afk_seconds, "afk"),
                   ev("10:17:30", 2400, "not-afk"))
        b = ab.work_bounds(sp)
        assert b is not None
        return ab.find_breaks(sp, b["work_start"], b["work_end"], ab.DEFAULT_THRESHOLD)

    assert [(hms(s), hms(e)) for s, e, _ in breaks_for(1050)] == [("10:00:00", "10:17:30")]
    assert breaks_for(1049) == []


def test_a_not_afk_run_of_exactly_two_minutes_counts_as_substantive_activity():
    """`last_solid_end` is where the skill is told to end the final block. A two-minute
    run counts, so the day ends at 09:02 and the late flicker is flagged. At 119 seconds
    nothing in the day qualifies as solid, `last_solid_end` falls back to `work_end`, the
    blip flag goes quiet — and the final block is stretched two hours to the flicker."""
    def bounds_for(solid_seconds):
        b = ab.work_bounds(spans(ev("09:00", solid_seconds, "not-afk"),
                                 ev("11:00", 1, "not-afk")))          # the flicker
        assert b is not None
        return b

    solid = bounds_for(120)
    assert hms(solid["last_solid_end"]) == "09:02:00"
    assert solid["blip"] is True

    flimsy = bounds_for(119)
    assert flimsy["last_solid_end"] == flimsy["work_end"] == at("11:00:01")
    assert flimsy["blip"] is False


def test_a_gap_of_exactly_ten_minutes_after_solid_activity_makes_work_end_a_blip():
    """The blip guard measures `work_end - last_solid_end`. At 600s the trailing nudge is
    called out and the block ends at 09:10; at 599s it is accepted as the end of the day
    and ten minutes of nothing get billed. Same solid anchor in both — this pins the gap
    comparison alone."""
    def bounds_for(flicker_at):
        b = ab.work_bounds(spans(ev("09:00", 600, "not-afk"),
                                 ev(flicker_at, 1, "not-afk")))
        assert b is not None
        return b

    wide = bounds_for("09:19:59")                     # flicker ends 09:20:00 -> gap 600
    assert hms(wide["last_solid_end"]) == "09:10:00"
    assert wide["blip"] is True

    narrow = bounds_for("09:19:58")                   # flicker ends 09:19:59 -> gap 599
    assert hms(narrow["last_solid_end"]) == "09:10:00"
    assert narrow["blip"] is False


def test_an_uncovered_segment_holding_exactly_fifteen_minutes_of_activity_is_reported():
    """The reporting floor counts *activity* inside the segment, not its wall clock: both
    days below leave the same 20 minutes of clock uncovered, and only the one holding a
    full 900 seconds of real work is worth telling the user about. A second under and a
    quarter hour of billable work disappears from the under-billing guard."""
    def gaps_for(head_seconds):
        sp = spans(ev("09:00", head_seconds, "not-afk"),
                   ev("09:15", 300, "afk"),           # short afk: folded into the span
                   ev("09:20", 6000, "not-afk"))
        active = ab.active_spans(sp, ab.DEFAULT_THRESHOLD)
        return ab.uncovered_segments(sp, active, [(at("09:20"), at("11:00"))])

    reported = gaps_for(900)
    assert [(hms(s), hms(e), secs) for s, e, secs in reported] == [("09:00:00", "09:20:00", 900)]
    assert gaps_for(899) == []


# --------------------------------------------------------------------------------------
# work_bounds
# --------------------------------------------------------------------------------------

def test_a_day_of_nothing_but_flickers_falls_back_to_work_end_and_never_flags_a_blip():
    """A day of sub-two-minute twitches has no substantive activity at all, so
    `max(..., default=work_end)` makes `last_solid_end` the day's end and the blip gap
    zero. `blip` is therefore structurally False here and carries no information.

    Pinned as correct, not merely current: `blip` exists to pull the final block back to
    the last substantive moment, and on this day there is no such moment to pull back to.
    A flag with no anchor beside it would tell the skill to end the block *somewhere*
    without saying where. The cost is that the day reports a full 09:00-17:01 shape with
    no warning attached — the sub-0.4 `active_ratio` checks in Step 3, not this flag, are
    what stop eight hours of twitching from being billed as eight hours of work."""
    b = ab.work_bounds(spans(*(ev(f"{h}:00", 60, "not-afk") for h in (9, 11, 13, 15, 17))))
    assert b is not None
    assert hms(b["work_start"]) == "09:00:00"
    assert b["last_solid_end"] == b["work_end"] == at("17:01")
    assert b["blip"] is False


def test_a_single_instantaneous_event_gives_a_day_that_starts_and_ends_at_one_moment():
    """AW can emit a zero-duration event when a watcher starts. It must not blow up the
    bounds or leave `work_end` missing: the day reads 09:00:00-09:00:00 with zero active
    minutes, which a reader has to interpret as "nothing happened", not as a day whose end
    the script failed to find and which is therefore open-ended."""
    sp = spans(ev("09:00", 0, "not-afk"))
    b = ab.work_bounds(sp)
    assert b is not None
    assert b["work_start"] == b["work_end"] == at("09:00")
    assert b["last_solid_end"] == b["work_end"]
    assert b["blip"] is False
    assert ab.total_active_seconds(sp) == 0


# --------------------------------------------------------------------------------------
# find_breaks — the workday comparison is inclusive at both ends
# --------------------------------------------------------------------------------------

def test_an_afk_run_starting_exactly_at_work_start_counts_as_a_break():
    """`s >= work_start` is inclusive, so an absence flush against the first not-afk moment
    of the day is inside the workday, not the not-at-work-yet idle before it. It shows up
    in the breaks list and the reader deducts it rather than billing from work_start."""
    sp = spans(ev("09:00", 1050, "afk"), ev("09:17:30", 3600, "not-afk"))
    breaks = ab.find_breaks(sp, at("09:00"), at("10:17:30"), ab.DEFAULT_THRESHOLD)
    assert [(hms(s), hms(e)) for s, e, _ in breaks] == [("09:00:00", "09:17:30")]


def test_an_afk_run_ending_exactly_at_work_end_counts_as_a_break():
    """`e <= work_end` is inclusive too. An absence that finishes on the last not-afk
    moment is still a break in the day, so a day that ends the instant the user comes back
    still reports the absence instead of quietly billing through it."""
    sp = spans(ev("09:00", 3600, "not-afk"), ev("10:00", 1050, "afk"))
    breaks = ab.find_breaks(sp, at("09:00"), at("10:17:30"), ab.DEFAULT_THRESHOLD)
    assert [(hms(s), hms(e)) for s, e, _ in breaks] == [("10:00:00", "10:17:30")]


def test_an_afk_run_straddling_work_end_is_left_out_of_the_breaks_list():
    """An absence that begins inside the day and runs past its end fails `e <= work_end`
    and vanishes from the list entirely — it is neither reported as a break nor trimmed to
    the day. That happens whenever the final not-afk moment lands *inside* a long absence
    (an auto-wake mid-afternoon, say): the breaks list then looks like an unbroken day.

    Pinned as current behaviour, not endorsed. It fails safe for billing — the ceiling is
    `work_end`, so the unreported afk is mostly outside the day anyway — but a reader
    taking the breaks list as the whole story misses that the day ended mid-absence."""
    sp = spans(ev("10:00", 3600, "afk"))              # 10:00-11:00, day ends 10:30
    assert ab.find_breaks(sp, at("09:00"), at("10:30"), ab.DEFAULT_THRESHOLD) == []


# --------------------------------------------------------------------------------------
# active_spans
# --------------------------------------------------------------------------------------

def test_overlapping_not_afk_events_produce_their_union_not_the_shorter_one():
    """AW can emit a short not-afk event inside a longer one. Taking the later event's end
    rather than the running maximum would cut the span back to 09:45 and hand a quarter
    hour of real work to the coverage check as unbilled time that was never missing."""
    sp = spans(ev("09:00", 3600, "not-afk"), ev("09:30", 900, "not-afk"))
    assert pairs(ab.active_spans(sp, ab.DEFAULT_THRESHOLD)) == [("09:00:00", "10:00:00")]


def test_active_spans_assumes_chronological_input_and_drops_earlier_activity_without_it():
    """`active_spans` walks the list once and only ever extends the current span forward,
    so an out-of-order event earlier than the open span is absorbed and lost: half an hour
    of real work disappears from the active spans and from the coverage check with it.

    The precondition is upheld by `dedupe_heartbeats`, which sorts — by the raw timestamp
    *string*. That is a chronological sort only because AW emits one fixed-width UTC
    spelling per stream, so lexical order matches time order. Timestamps carrying a real
    zone offset (`...+13:00`), or a stream mixing `Z` with `+00:00`, would sort wrong and
    land in exactly the case below, which is why nothing may feed this function raw events
    that skipped the dedupe step."""
    unsorted = [ev("10:00", 3600, "not-afk"), ev("09:00", 1800, "not-afk")]
    assert pairs(ab.active_spans(ab.to_spans(unsorted), ab.DEFAULT_THRESHOLD)) == [
        ("10:00:00", "11:00:00")]           # the 09:00-09:30 work is simply gone

    deduped = ab.to_spans(ab.dedupe_heartbeats(unsorted))
    assert pairs(ab.active_spans(deduped, ab.DEFAULT_THRESHOLD)) == [("09:00:00", "11:00:00")]


def test_a_day_opening_with_a_long_afk_run_does_not_emit_an_empty_leading_span():
    """Every morning starts with hours of over-threshold afk before the first keystroke.
    Splitting on it while no span is open would emit a zero-length span at 07:00 and put a
    phantom block at the top of every timesheet."""
    sp = spans(ev("07:00", 5400, "afk"), ev("08:30", 3600, "not-afk"))
    assert pairs(ab.active_spans(sp, ab.DEFAULT_THRESHOLD)) == [("08:30:00", "09:30:00")]


def test_a_zero_duration_event_becomes_a_zero_length_active_span():
    """A zero-duration not-afk opens a span that a following real break closes at the same
    instant, so the report grows an `08:00:00 - 08:00:00 (0.0 min)` line.

    Cosmetic, and pinned as such: the span holds no activity, so it cannot reach the
    coverage report (0 < MIN_UNCOVERED_S) and cannot add billable minutes anywhere. The
    only cost is a reader wondering what that line means."""
    sp = spans(ev("08:00", 0, "not-afk"), ev("08:00", 1800, "afk"), ev("09:00", 3600, "not-afk"))
    active = ab.active_spans(sp, ab.DEFAULT_THRESHOLD)
    assert pairs(active) == [("08:00:00", "08:00:00"), ("09:00:00", "10:00:00")]
    assert ab.active_seconds(sp, at("08:00"), at("08:00")) == 0
    assert ab.uncovered_segments(sp, active, []) == [(at("09:00"), at("10:00"), 3600)]


# --------------------------------------------------------------------------------------
# active_seconds
# --------------------------------------------------------------------------------------

def test_a_window_that_ends_before_it_starts_reads_as_zero_rather_than_negative():
    """`main()` rejects a reversed `--window` in `parse_range`, but the function itself is
    called directly by `uncovered_segments` and would return a negative total if the
    clipping test were `>=` instead of `>`. Zero is the safe answer: a reversed window
    reads as "mostly idle", never as a window that subtracts time from the day."""
    sp = spans(ev("09:00", 3600, "not-afk"))
    assert ab.active_seconds(sp, at("11:00"), at("10:00")) == 0.0


def test_a_window_wholly_inside_one_event_counts_only_the_window():
    """The Step 3 ratio for a 15-minute slice of a solid hour must be 15 minutes of
    activity, not the whole event — otherwise every short window scores over 1.0 and the
    idle-detection bands stop meaning anything."""
    sp = spans(ev("09:00", 3600, "not-afk"))
    assert ab.active_seconds(sp, at("09:10"), at("09:25")) == 900


def test_a_window_spanning_several_events_counts_their_overlaps_and_not_the_gaps():
    """65 minutes of clock holding 25 minutes of work has to read as 25, or the ratio that
    is supposed to catch a dead stretch reports it as a solid block of work."""
    sp = spans(ev("09:00", 600, "not-afk"),        # 09:05-09:10 counts:  5 min
               ev("09:10", 1200, "afk"),           # idle, ignored
               ev("09:30", 600, "not-afk"),        # 09:30-09:40 counts: 10 min
               ev("10:00", 1200, "not-afk"))       # 10:00-10:10 counts: 10 min
    assert ab.active_seconds(sp, at("09:05"), at("10:10")) == 25 * 60


# --------------------------------------------------------------------------------------
# uncovered_segments — the under-billing guard
# --------------------------------------------------------------------------------------

def _four_hour_span():
    """09:00-13:00 of unbroken activity, and the active span it produces."""
    sp = spans(ev("09:00", 4 * 3600, "not-afk"))
    return sp, ab.active_spans(sp, ab.DEFAULT_THRESHOLD)


def test_proposed_blocks_given_out_of_order_are_all_subtracted():
    """Blocks come from a model listing them in whatever order it drafted them. If the
    subtraction assumed chronological order, an afternoon block written before a morning
    one would leave the morning reported as unbilled and send the user chasing work they
    already billed."""
    sp, active = _four_hour_span()
    proposed = [(at("11:00"), at("12:00")), (at("09:00"), at("10:00"))]
    assert [(hms(s), hms(e)) for s, e, _ in ab.uncovered_segments(sp, active, proposed)] == [
        ("10:00:00", "11:00:00"), ("12:00:00", "13:00:00")]


def test_overlapping_proposed_blocks_do_not_subtract_twice_or_invert_a_segment():
    """Two blocks that overlap (a Harvest entry extended past the next one's start) must
    remove their union once. Subtracting each independently would produce a segment with
    its end before its start and report negative work."""
    sp, active = _four_hour_span()
    proposed = [(at("09:00"), at("11:00")), (at("10:00"), at("12:00"))]
    gaps = ab.uncovered_segments(sp, active, proposed)
    assert [(hms(s), hms(e), secs) for s, e, secs in gaps] == [("12:00:00", "13:00:00", 3600)]


def test_a_proposed_block_swallowing_a_whole_active_span_leaves_nothing_uncovered():
    """One block billed generously across a short span covers it completely. Reporting a
    remainder here would flag work that is already on the invoice."""
    sp = spans(ev("09:00", 3600, "not-afk"))
    active = ab.active_spans(sp, ab.DEFAULT_THRESHOLD)
    assert ab.uncovered_segments(sp, active, [(at("08:00"), at("17:00"))]) == []


def test_a_proposed_block_inside_an_active_span_leaves_a_gap_on_each_side():
    """Billing only the middle of a four-hour stretch has to surface both ends. Keeping
    just one side would hide an hour of work per day, every day."""
    sp, active = _four_hour_span()
    gaps = ab.uncovered_segments(sp, active, [(at("10:00"), at("11:00"))])
    assert [(hms(s), hms(e)) for s, e, _ in gaps] == [("09:00:00", "10:00:00"),
                                                      ("11:00:00", "13:00:00")]


def test_a_block_splitting_a_span_reports_only_the_piece_above_the_reporting_floor():
    """The same block leaves a 10-minute head and a 1-hour tail. The head is block rounding
    and must stay silent or the guard cries wolf on every timesheet; the tail is an unbilled
    hour and must not be silenced along with it."""
    sp, active = _four_hour_span()
    gaps = ab.uncovered_segments(sp, active, [(at("09:10"), at("12:00"))])
    assert [(hms(s), hms(e), secs) for s, e, secs in gaps] == [("12:00:00", "13:00:00", 3600)]


def test_a_proposed_block_outside_every_active_span_leaves_the_report_intact():
    """A stretch deliberately excluded from the day (personal browsing, a meeting billed
    elsewhere) can be proposed over time the AFK watcher saw no activity in. It must pass
    through the subtraction without clipping, splitting or dropping a real span — the
    morning is still reported in full, and adding it to the proposal still clears it."""
    sp = spans(ev("09:00", 7200, "not-afk"))          # 09:00-11:00
    active = ab.active_spans(sp, ab.DEFAULT_THRESHOLD)
    outside = (at("13:00"), at("14:00"))

    assert ab.uncovered_segments(sp, active, [outside]) == [(at("09:00"), at("11:00"), 7200)]
    assert ab.uncovered_segments(sp, active, [outside, (at("09:00"), at("11:00"))]) == []
