"""Tests for the shared zone arithmetic.

The zone a day is read in, the bounds it gives the day, and the two dates a year on which
a clock reading is not a straight fact. These lived in `test_aw_client.py` until #36, when
the arithmetic moved out of the activity-source client and into `timezone.py` — both halves
of the skill need it, and the provider scripts were importing that client to reach it. Not
an assertion here changed in the move.

The two day-reading scripts are imported at the bottom, to assert they really use the
shared functions rather than their own; the provider half's use of the same module is in
`test_edge_harvest_api.py`, at the refusal that reads it.
"""

import datetime as dt
import os
import sys
from zoneinfo import ZoneInfo

import pytest

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts")
sys.path.insert(0, SCRIPTS)
import timezone as tz
import activity_timeline as tl
import afk_blocks as ab
from support import fixed


def test_utc_bounds_spans_local_midnight_to_local_midnight():
    """NZST is UTC+12, so a local day starts at 12:00Z the day before."""
    start, end = tz.utc_bounds(dt.date(2026, 5, 28), fixed(12))
    assert (start, end) == ("2026-05-27T12:00:00Z", "2026-05-28T12:00:00Z")


# --------------------------------------------------------------------------------------
# The hour the clocks repeat
#
# `Pacific/Auckland` goes back at 03:00 on 2026-04-05, so local 02:00-03:00 happens twice:
# once at UTC+13 (2026-04-04 13:00Z-14:00Z) and again at UTC+12 (14:00Z-15:00Z). Without a
# marker both passes render `02:30:00`, and the two instants an hour apart are one string.
# --------------------------------------------------------------------------------------

NZ = ZoneInfo("Pacific/Auckland")
FIRST_PASS = dt.datetime(2026, 4, 4, 13, 30, tzinfo=dt.timezone.utc)    # 02:30 NZDT
SECOND_PASS = dt.datetime(2026, 4, 4, 14, 30, tzinfo=dt.timezone.utc)   # 02:30 NZST


def test_local_clock_marks_only_the_second_pass_over_the_repeated_hour():
    """The whole point: two instants an hour apart must not print the same string."""
    assert tz.local_clock(FIRST_PASS, NZ) == "02:30:00"
    assert tz.local_clock(SECOND_PASS, NZ) == "02:30:00*"


@pytest.mark.parametrize("moment", [
    dt.datetime(2026, 4, 4, 12, 30, tzinfo=dt.timezone.utc),   # 01:30, before the change
    dt.datetime(2026, 4, 4, 15, 30, tzinfo=dt.timezone.utc),   # 03:30, after it
    dt.datetime(2026, 4, 4, 21, 0, tzinfo=dt.timezone.utc),    # 09:00, later the same day
], ids=["before", "after", "well-after"])
def test_local_clock_leaves_unambiguous_times_on_a_transition_day_unmarked(moment):
    """The marker costs the reader nothing on the other twenty-four hours of the day."""
    assert not tz.local_clock(moment, NZ).endswith("*")


def test_local_clock_never_marks_a_fixed_offset_zone():
    """`--utc-offset` means a zone that is that offset all year, so it has no repeated
    hour to mark and no run passing a number should ever grow the character."""
    assert tz.local_clock(SECOND_PASS, fixed(12)) == "02:30:00"


def test_parse_local_time_reads_the_marker_as_the_second_pass():
    assert tz.parse_local_time("02:30").fold == 0
    assert tz.parse_local_time("02:30*").fold == 1
    # Asserted field by field: `time.__eq__` ignores `fold`, so comparing against a
    # `dt.time(2, 30)` would pass whether or not the marker had been read at all.
    marked = tz.parse_local_time("02:30:00*")
    assert (marked.hour, marked.minute, marked.second, marked.fold) == (2, 30, 0, 1)


def test_a_marker_on_a_time_the_clock_reads_only_once_is_refused():
    """`zoneinfo` drops `fold` on an unambiguous reading, so without this `09:00*` would
    quietly mean `09:00` — a marker that means something only sometimes, with nothing in
    the output to say which time it was."""
    with pytest.raises(ValueError, match="only once"):
        tz.to_utc(dt.date(2026, 4, 5), tz.parse_local_time("09:00*"), NZ)


def test_the_marker_is_refused_on_the_far_edge_of_the_repeated_hour():
    """03:00 is the one reading in the neighbourhood that is *not* ambiguous: the clock
    reaches 03:00 once, an hour after the change. `03:00*` resolving silently to `03:00`
    is the specific mistake this catches, because it reads like it names the transition."""
    with pytest.raises(ValueError, match="only once"):
        tz.to_utc(dt.date(2026, 4, 5), tz.parse_local_time("03:00*"), NZ)


def test_a_marker_is_refused_in_a_zone_that_never_repeats_an_hour():
    with pytest.raises(ValueError, match="only once"):
        tz.to_utc(dt.date(2026, 4, 5), tz.parse_local_time("02:30*"), fixed(12))


def test_the_transition_instant_is_nameable_only_as_a_marked_time():
    """The first instant of the new offset. `02:00` is an hour before it and `03:00` an
    hour after, so `02:00*` is the only clock string that names it — which is why
    `output-format.md` tells the model to split a straddling entry there."""
    transition = dt.datetime(2026, 4, 4, 14, 0, tzinfo=dt.timezone.utc)
    assert tz.to_utc(dt.date(2026, 4, 5), tz.parse_local_time("02:00*"), NZ) == transition
    assert tz.local_clock(transition, NZ) == "02:00:00*"


# --------------------------------------------------------------------------------------
# Locating the change itself. `zoneinfo` publishes no transition list, so this is found by
# bisection — and the zones below are the ones that break the obvious ways of reading it.
# --------------------------------------------------------------------------------------

def test_the_two_readings_of_a_fall_back_come_back_in_the_order_they_are_read_in():
    """`03:00` as the instant arrives and `02:00` once it has passed, which is the pair a
    create turns into the two entries a straddling one has to become."""
    assert tz.transition_clocks(dt.date(2026, 4, 5), NZ) == (dt.time(3, 0), dt.time(2, 0), True)


def test_a_spring_forward_is_the_same_pair_the_other_way_round():
    assert tz.transition_clocks(dt.date(2026, 9, 27), NZ) == (dt.time(2, 0), dt.time(3, 0), False)


@pytest.mark.parametrize("date,zone", [
    (dt.date(2026, 5, 28), NZ),          # an ordinary day in a zone that does change
    (dt.date(2026, 4, 5), fixed(12)),    # the transition date, in a `--utc-offset` zone
], ids=["ordinary-day", "fixed-offset-zone"])
def test_a_day_whose_clocks_do_not_change_reports_no_transition(date, zone):
    """The answer on all but two dates a year, and what keeps every caller's behaviour on
    those dates exactly what it was."""
    assert tz.transition_clocks(date, zone) is None


def test_a_change_that_is_not_a_whole_hour_is_read_at_its_real_size():
    """`Australia/Lord_Howe` moves by thirty minutes, so the span that happens twice is
    01:30-02:00. Nothing may assume the shift is an hour: the two entries a straddling
    create becomes are measured off these two readings, and an assumed hour would start the
    second one at 01:00 — half an hour too early, billing thirty minutes nobody worked."""
    assert tz.transition_clocks(dt.date(2026, 4, 5), ZoneInfo("Australia/Lord_Howe")) == \
        (dt.time(2, 0), dt.time(1, 30), True)


def test_clocks_that_go_back_at_midnight_are_still_read_as_going_back():
    """`America/Santiago` returns to 23:00 as the clock reaches 00:00, so its two readings
    arrive in the *opposite* order to New Zealand's — the later one second. Reading the
    direction off that order gets this day exactly backwards and would leave a genuine
    fall-back treated as a spring-forward, so the direction comes from the offset shift."""
    got = tz.transition_clocks(dt.date(2026, 4, 4), ZoneInfo("America/Santiago"))
    assert got is not None and got == (dt.time(0, 0), dt.time(23, 0), True)
    assert got.once_passed > got.as_reached, "the reason the order cannot be the test"


def test_the_reading_taken_at_face_value_is_an_hour_after_the_instant_it_names():
    """The trap the whole refusal is built around, pinned at the arithmetic. The clocks go
    back at 14:00Z; that instant reads `03:00` as it arrives, but `03:00` written as a
    plain time on that date means 15:00Z, an hour later. Only `02:00*` names the instant
    itself — which is why the two replacement entries read as though they overlap."""
    date, change = dt.date(2026, 4, 5), tz.transition_clocks(dt.date(2026, 4, 5), NZ)
    assert change is not None
    transition = dt.datetime(2026, 4, 4, 14, 0, tzinfo=dt.timezone.utc)
    assert tz.to_utc(date, tz.parse_local_time("02:00*"), NZ) == transition
    assert tz.to_utc(date, tz.parse_local_time(change.as_reached.strftime("%H:%M")), NZ) \
        == transition + dt.timedelta(hours=1)


@pytest.mark.parametrize("written,expected", [("02:30", FIRST_PASS), ("02:30*", SECOND_PASS)])
def test_to_utc_resolves_each_pass_to_its_own_instant(written, expected):
    got = tz.to_utc(dt.date(2026, 4, 5), tz.parse_local_time(written), NZ)
    assert got == expected


@pytest.mark.parametrize("moment", [FIRST_PASS, SECOND_PASS])
def test_a_rendered_clock_reads_back_as_the_instant_it_came_from(moment):
    """The round trip is the reason for the marker: a time the model reads out of one
    script's output has to name the same instant when fed back as `--window` / `--cover`."""
    written = tz.local_clock(moment, NZ)
    assert tz.to_utc(dt.date(2026, 4, 5), tz.parse_local_time(written), NZ) == moment


def test_parse_range_spanning_the_repeated_hour_is_an_hour_long():
    """The sharpest instance: an hour-long break from the first 02:30 to the second one.
    Unmarked, both ends resolve to the same instant and the range reads as empty — which
    `parse_range` rejects outright as a reversed range."""
    ws, we = tz.parse_range("02:30:00-02:30:00*", dt.date(2026, 4, 5), NZ)
    assert (we - ws) == dt.timedelta(hours=1)
    assert (ws, we) == (FIRST_PASS, SECOND_PASS)


def test_parse_range_reads_a_block_wholly_inside_the_second_pass():
    ws, we = tz.parse_range("02:00*-03:00", dt.date(2026, 4, 5), NZ)
    assert (ws, we) == (dt.datetime(2026, 4, 4, 14, 0, tzinfo=dt.timezone.utc),
                        dt.datetime(2026, 4, 4, 15, 0, tzinfo=dt.timezone.utc))


@pytest.mark.parametrize("rng", ["02:30*-02:45", "02:00*-02:30"])
def test_parse_range_names_the_unmarked_end_rather_than_a_spring_forward(rng):
    """A marker on the start only is a reversed range, and the reason is the *end*: it
    resolves to the first pass, an hour before the marked start. Nothing is skipped on a
    fall-back day, so a message about the hour the clocks skip sends the reader hunting a
    transition that is six months away. `02:00*-02:30` is what a model writes after
    `output-format.md` tells it the split point is `02:00*`, so this is the likely typo."""
    with pytest.raises(ValueError) as exc:
        tz.parse_range(rng, dt.date(2026, 4, 5), NZ)
    assert "skip" not in str(exc.value)
    assert "start only" in str(exc.value)


# --------------------------------------------------------------------------------------
# The hour the clocks skip
#
# `Pacific/Auckland` goes forward at 02:00 on 2026-09-27, so local 02:00-03:00 never
# happens: no instant on that date carries those readings. The marker names the second
# pass over a *repeated* hour, so inside this one it names nothing — and `zoneinfo`
# resolves it to the offset in force *after* the change, an hour earlier than the same
# reading unmarked, which is the wrong direction as well as the wrong hour.
# --------------------------------------------------------------------------------------

SPRING = dt.date(2026, 9, 27)


@pytest.mark.parametrize("written", ["02:00*", "02:30*", "02:59*"])
def test_the_marker_is_refused_inside_the_hour_the_clocks_skip(written):
    """The guard used to compare the two offsets for inequality alone. Inside a gap they
    differ, so the marker sailed through and landed an hour early — `02:30*` reporting on
    01:30. Telling a gap from a repeated hour needs the *sign* of the difference."""
    with pytest.raises(ValueError, match="never reads"):
        tz.to_utc(SPRING, tz.parse_local_time(written), NZ)


@pytest.mark.parametrize("rng", ["02:15*-02:45*", "02:15*-02:45", "02:15-02:45*"])
def test_a_window_marked_inside_the_skipped_hour_is_refused(rng):
    """`02:15*-02:45*` was accepted and silently reported on 01:15-01:45; `02:15*-02:45`
    yielded ninety minutes from a thirty-minute clock range. Both now stop at the marker
    rather than producing a plausible wrong answer."""
    with pytest.raises(ValueError, match="never reads"):
        tz.parse_range(rng, SPRING, NZ)


@pytest.mark.parametrize("rng", ["02:30-03:30", "02:00-03:00", "02:30-03:00"])
def test_parse_range_names_the_skipped_hour_when_a_range_spans_it(rng):
    """Ordered on the clock and empty in real time. Falling through to "end must be after
    start" would send the user hunting a typo they did not make. `test_afk_blocks.py`
    already covers `02:00-03:00` through one script's re-export; this pins the shared
    module, and the two neighbouring shapes that reverse rather than collapse."""
    with pytest.raises(ValueError, match="spans the hour the clocks skip"):
        tz.parse_range(rng, SPRING, NZ)


def test_an_unmarked_reading_inside_the_skipped_hour_takes_the_instant_the_clock_reached():
    """The standing convention, pinned rather than changed: `02:30` on the spring morning
    is the instant a clock left at the wall would next have shown, 03:30 at the new
    offset. It is a convention and not a fact, but both scripts read the same one."""
    got = tz.to_utc(SPRING, tz.parse_local_time("02:30"), NZ)
    assert got == dt.datetime(2026, 9, 26, 14, 30, tzinfo=dt.timezone.utc)


# `parse_range` joined this list on 2026-08-14: the two scripts had separate copies that
# disagreed about a reversed range, so one errored and the other printed an empty result
# for the same typo. That is the drift the shared modules exist to prevent, and the reason
# the list is asserted on rather than trusted — a private copy reads identically at the
# call site.
SHARED = ["resolve_zone", "zone_label", "utc_bounds", "local_clock", "parse_range"]


@pytest.mark.parametrize("module", [ab, tl], ids=["afk_blocks", "activity_timeline"])
@pytest.mark.parametrize("name", SHARED)
def test_the_day_reading_scripts_use_the_shared_zone_helper_rather_than_their_own(module, name):
    """A private copy would be a different function object; the same object proves reuse."""
    assert getattr(module, name, None) is getattr(tz, name), (
        f"{module.__name__}.{name} is not the shared timezone one"
    )
