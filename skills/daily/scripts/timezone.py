"""The zone a day is read in, and the clock arithmetic that follows from it.

Both halves of this skill need this and neither owns it. The day-reading scripts need it to
bound a day, to parse a `--window` and to render an instant a person will read; the provider
scripts need it to tell whether an entry runs through a clock change that would bill it
short. It lived in `aw_client.py` until #36, which meant `harvest_post.py` and
`harvest_patch.py` imported the activity-source client to get at it — the one import edge
that ran the wrong way, and one an adapter behind a boundary cannot have. Nothing about the
functions changed in the move; only where they live.

So this module knows about neither side: it reads the configured zone through
`skill_config`, like everything else here, and imports nothing else of this skill's.
`tests/test_module_boundaries.py` holds that.

**A zone, not an offset.** A day does not necessarily have one offset — on the two dates a
year the clocks change it has two — so every conversion below takes the zone itself and
resolves each instant at the offset in force for *it*. `resolve_zone()` says what a single
figure read once cost.

No third-party deps — stdlib `zoneinfo`, like the sibling modules.
"""
import datetime as dt
from typing import NamedTuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import skill_config


def resolve_zone(flag, offers_offset_flag: bool = True):
    """The timezone this day's local clock is read in.

    `flag` is whatever `--utc-offset` supplied, or None; it wins, so a day spent in
    another zone can still be reconstructed without reconfiguring anything. It resolves to
    a zone that is that offset all year, which is what passing a number has always meant.
    Otherwise the configured `TIMESHEET_TIMEZONE` is loaded.

    `offers_offset_flag=False` says the calling script has no such per-run override —
    which the provider scripts have not, carrying no flags but their fields and the
    confirmation gate. The messages below then stop naming `--utc-offset`, rather than
    sending a user who is already stuck to try one more thing that would come back as a
    usage error.

    A boolean and not the flag's own spelling, which is what it was first written as: a
    bare `"--utc-offset"` default here is indistinguishable from a flag *this* module
    parses, and `tests/test_references.py` said so — it reads the flags out of each
    script's syntax tree and wanted this one added to the inventory entry of the module
    this used to live in, where it would tell every run that a module with no command line
    takes an argument. There is one spelling of the flag either way, so nothing is lost by
    not passing it.

    A zone rather than a number, because a day does not necessarily have *one* offset.
    This used to answer with a single figure read at local noon, and on the day the clocks
    change that is wrong at both ends of the day at once: the fetch window opens an hour
    late or early, and every event on the far side of the transition renders an hour out.
    Neither failure raises anything — the day simply reads short and starts in the wrong
    place. Handing the zone itself to the arithmetic below lets each instant be converted
    at the offset in force for *it*.

    There is deliberately no fallback. This used to be `default=12.0` in both day-reading
    scripts' argument parsers, so every user who was not in New Zealand got a day boundary
    up to twelve hours out — and, again, nothing failed. No offset is safe to guess, so an
    unconfigured run stops and says which value it needs.
    """
    if flag is not None:
        try:
            return dt.timezone(dt.timedelta(hours=flag))
        except (ValueError, OverflowError):
            # Every other bad input to these scripts produces a line and a non-zero exit;
            # one that escaped from here would be the single traceback, and a traceback
            # tells a model reading this that the tool is broken rather than that the
            # number is. Both exception types, because `argparse type=float` takes `inf`
            # as readily as `99` and the timedelta constructor answers them differently.
            skill_config.fail_missing(
                f"--utc-offset {flag} is not an offset any zone has.\n"
                "  It is hours from UTC, between -24 and 24, e.g. 13 or -5.5.")
    name = skill_config.setting("TIMESHEET_TIMEZONE")
    if not name:
        skill_config.fail_missing(
            ("No timezone configured, and no --utc-offset given.\n" if offers_offset_flag
             else "No timezone configured.\n") +
            "  Your zone decides where a day begins and ends, and when the clocks change\n"
            "  inside it, so there is nothing safe to assume.\n"
            "  Set it once:  /plugin configure billables  -> TIMESHEET_TIMEZONE\n"
            "                (an IANA name, e.g. Europe/London or Pacific/Auckland)\n"
            "  Already set it? Start a new session — the value is published at session\n"
            "  start. If a new session still shows this, see references/setup.md\n"
            "  § 'When the configuration does not arrive'." +
            ("\n  Or for this run only:  --utc-offset <hours>" if offers_offset_flag else "")
            # Last, after the escape hatch, because it is the cause a user cannot deduce
            # and the two lines above are the wrong advice for it. Shared with
            # `harvest_client.load_creds()`: one absence, one cause, one wording.
            + skill_config.note_for_an_unreached_shell())
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        skill_config.fail_missing(
            f"Could not load the timezone '{name}' ({exc}).\n"
            "  Check it against the IANA list (e.g. Europe/London, Pacific/Auckland).\n"
            "  On Windows the zone database is a separate install:  pip install tzdata" +
            ("\n  Or bypass it for this run:  --utc-offset <hours>" if offers_offset_flag
             else ""))


def zone_label(zone):
    """How a resolved zone names itself in a header a person reads.

    A real zone is named, because on a transition day no single offset describes it and
    printing one would be a claim the run is not making. A `--utc-offset` zone keeps the
    wording it always had, since that is exactly what the user typed.
    """
    key = getattr(zone, "key", None)
    if key:
        return f"zone {key}"
    return f"offset UTC{zone.utcoffset(None).total_seconds() / 3600:+g}"


SECOND_PASS_MARK = "*"


def parse_local_time(s):
    """Parse 'HH:MM' or 'HH:MM:SS' to a datetime.time, reading a trailing `*`.

    The `*` is how a caller names the *second* pass over the hour a fall-back repeats —
    the shape `local_clock()` writes — and it survives as the returned time's `fold`,
    which `to_utc()` then honours. Without it the plain reading stands, so every time
    written before this existed still means what it did.
    """
    s = s.strip()
    fold = 0
    if s.endswith(SECOND_PASS_MARK):
        s, fold = s[:-len(SECOND_PASS_MARK)].strip(), 1
    fmt = "%H:%M:%S" if s.count(":") == 2 else "%H:%M"
    return dt.datetime.strptime(s, fmt).time().replace(fold=fold)


READS_ONCE, READS_TWICE, READS_NEVER = "once", "twice", "never"


def clock_reads(local_date, local_time, zone):
    """How many times a clock in `zone` reaches this reading on this date — `READS_ONCE`
    on any ordinary reading, `READS_TWICE` inside the hour a fall-back repeats,
    `READS_NEVER` inside the hour a spring-forward skips.

    The two transition hours are told apart by the *sign* of the offset shift across
    `fold`, not by the fact that there is one. Under PEP 495 `fold=0` always means the
    offset in force before the change and `fold=1` the one after, so a repeated hour
    shifts backwards (in `Pacific/Auckland`, +13 to +12) and a skipped hour forwards (+12
    to +13). Asking only whether the two differ cannot separate them, and the callers
    below need to: a marker means one thing in a repeated hour and nothing at all in a
    skipped one.
    """
    moment = dt.datetime.combine(local_date, local_time, tzinfo=zone)
    # How far apart in real time the two passes sit. Measured by converting each to UTC
    # rather than by subtracting the two `utcoffset()`s, which is the same quantity —
    # an instant is its clock reading minus its offset, so the offsets cancel the other
    # way round — but is not typed as possibly absent the way an offset is.
    shift = (moment.replace(fold=0).astimezone(dt.timezone.utc)
             - moment.replace(fold=1).astimezone(dt.timezone.utc))
    if shift < dt.timedelta(0):
        return READS_TWICE
    if shift > dt.timedelta(0):
        return READS_NEVER
    return READS_ONCE


def to_utc(local_date, local_time, zone):
    """A wall-clock time on a local date, as the UTC instant it names in `zone`.

    The single place a local clock becomes an instant, so the transition-day answer is the
    same for a day boundary, a `--window` and a `--cover` block. On the hour a fall-back
    repeats, the wall clock is genuinely ambiguous, and this resolves it to whichever pass
    `local_time.fold` asks for — the first unless the caller marked it, which is what an
    unmarked time has always meant. On the hour a spring-forward skips, an *unmarked*
    reading takes the instant the clock would have reached. Both are conventions rather
    than facts — but only inside that one hour, and both scripts read the same one.

    A marker on a time the clock does not read twice is refused rather than ignored, and
    the two ways that happens are named apart. `zoneinfo` drops `fold` on an unambiguous
    reading, so `09:00*` would quietly mean `09:00` — a marker that sometimes carries
    meaning is worse than one that always does, because nothing in the output
    distinguishes the two cases. Inside a skipped hour `zoneinfo` does the opposite and
    honours `fold`, resolving `02:30*` an hour *earlier* than `02:30`, so the marker there
    used to be accepted and quietly report on a different hour than the one asked for.
    """
    moment = dt.datetime.combine(local_date, local_time, tzinfo=zone)
    if local_time.fold:
        reads = clock_reads(local_date, local_time, zone)
        clock = local_time.strftime("%H:%M:%S")
        opening = (f"'{clock}{SECOND_PASS_MARK}' names a second pass over a repeated "
                   f"hour, but ")
        if reads == READS_NEVER:
            raise ValueError(
                f"{opening}the clock never reads {clock} on {local_date} in this zone — "
                f"the clocks go forward at that hour, so no instant on that date carries "
                f"that reading at all")
        if reads == READS_ONCE:
            raise ValueError(
                f"{opening}the clock reads {clock} only once on {local_date} in this "
                f"zone — drop the '{SECOND_PASS_MARK}'")
    return moment.astimezone(dt.timezone.utc)


def _offset_at(moment, zone):
    """The offset in force at an instant, as a timedelta.

    By subtracting the two renderings rather than by asking `utcoffset()`, which is typed
    as possibly absent and is not, for the same reason `clock_reads` converts to UTC
    instead. Both operands are made naive first: a naive difference is the offset, where
    an aware one would be zero by construction.
    """
    return moment.astimezone(zone).replace(tzinfo=None) - moment.replace(tzinfo=None)


class Transition(NamedTuple):
    """The one clock change on a date: its two readings, and which way it went."""
    as_reached: dt.time         # what the clock said as the instant arrived
    once_passed: dt.time        # what it said immediately afterwards
    repeats: bool               # True if the span between them happens twice, not never


def transition_clocks(local_date, zone):
    """The clock change on `local_date`, or None if there isn't one.

    In `Pacific/Auckland` on 2026-04-05 the clocks go back at one instant that reads
    `03:00` as you arrive at it and `02:00` afterwards, so this answers
    `(03:00, 02:00, repeats=True)`; on the spring-forward day it answers
    `(02:00, 03:00, repeats=False)`, the same pair the other way round.

    `repeats` comes from the sign of the offset shift and not from comparing the two
    readings, which is the same distinction `clock_reads` draws and for a sharper reason
    here: a zone whose clocks go back at midnight reads `00:00` as it arrives and `23:00`
    once passed, so "the later reading came second" gets that day exactly backwards.
    `America/Santiago` does this every April.

    None on every other day, which is the answer for all but two dates a year and the one
    that keeps a caller's behaviour on those dates exactly what it was.

    Found by bisection because `zoneinfo` publishes no transition list — there is no
    supported way to ask a zone when it next changes, only what its offset is at a given
    instant. The day is bracketed by its own two midnights, resolved in the zone the way
    `utc_bounds` resolves them, so a day that is 23 or 25 hours long is searched at its
    real length. A second transition inside one day would be missed; no zone has had one
    since the standard-time era, and a day with two would break far more than this.
    """
    lo = to_utc(local_date, dt.time(0, 0), zone)
    hi = to_utc(local_date + dt.timedelta(days=1), dt.time(0, 0), zone)
    before, after = _offset_at(lo, zone), _offset_at(hi, zone)
    if before == after:
        return None
    while hi - lo > dt.timedelta(seconds=1):
        mid = lo + (hi - lo) / 2
        if _offset_at(mid, zone) == before:
            lo = mid
        else:
            hi = mid
    # `hi` is now the first instant past the change, within a second of it. Transitions
    # land on a minute boundary, so flooring recovers the instant itself exactly — and the
    # readings below are wanted to the minute regardless, since that is what a time entry
    # is written in.
    moment = hi.replace(second=0, microsecond=0)
    return Transition((moment + before).time(), (moment + after).time(), after < before)


def _minutes(t: dt.time) -> int:
    """A clock reading as minutes since midnight, the unit `repeated_span()` answers in."""
    return t.hour * 60 + t.minute


def repeated_span(spent, zone) -> tuple[int, int] | None:
    """The minutes-since-midnight bounds of the span the clocks repeat on `spent`, or None.

    Measured, never assumed: `Australia/Lord_Howe` moves thirty minutes and
    `Antarctica/Troll` two hours, and both figures come off the zone's own two readings.

    None means there is nothing on this date an entry could straddle, which is three
    different facts and not one:

    - no transition at all, which is every date but two a year;
    - a spring-forward. The clock skips rather than repeating, so an entry across it is
      over-billed rather than short, and its two pieces would be separated by a gap where
      these two abut — a different message, and #23 put it out of scope. The `TESTING.md`
      Open gaps entry for the skipped hour carries it. `repeats` comes from the sign of
      the offset shift and not from the order of the two readings, which gets
      `America/Santiago` exactly backwards;
    - a repeated span that crosses midnight, as it does in `America/Santiago`, where the
      clocks go back at 00:00 to 23:00. Containment would then need an end past 1440, and
      a clock reading caps at 23:59 — so a span that opens at 23:00 and closes at 00:00
      reads as `(1380, 0)`, and the guard is the `repeat_open >= repeat_close` line rather
      than a special case for that zone.

    Answered in minutes since midnight, not as the two `time`s the transition carries,
    because the callers compare it against an interval — and a caller that did its own
    conversion would be the second place the midnight-crossing case has to be got right.
    `harvest_write.py`'s `refusal_for_a_straddled_change()` is the one that decides what to
    do about a straddle; this is the cheap half of the question it asks first, and
    `harvest_patch.py` asks it directly for that reason: on a date with no repeated span it
    can skip reading the entry it is about to patch, which is a request over the wire.

    Here and not beside that refusal because the answer is the zone's: what the clocks did
    on a date is the same fact whoever is billing it, and how a provider bills across it is
    not.
    """
    change = transition_clocks(spent, zone)
    if change is None or not change.repeats:
        return None
    repeat_open, repeat_close = _minutes(change.once_passed), _minutes(change.as_reached)
    if repeat_open >= repeat_close:
        return None
    return repeat_open, repeat_close


def parse_range(rng, local_date, zone):
    """Parse a local 'HH:MM-HH:MM' (seconds optional) to an aware UTC (start, end) pair.

    Raises ValueError on a bad format or a reversed/empty range. Shared because both
    day-reading scripts take a `--window` in this shape and each used to parse it its own
    way: the afk one rejected `17:00-09:00`, the timeline one accepted it and printed an
    empty result, so the same typo produced an error in one script and a plausible-looking
    "nothing happened then" in the other.

    A range that runs backwards in real time has three causes on a transition day, and
    each gets its own message. Naming the wrong one is worse than naming none: a range
    refused for spanning a spring-forward on the day the clocks went *back* sends the
    reader hunting a transition six months away.
    """
    a, b = rng.split("-", 1)
    lo, hi = parse_local_time(a), parse_local_time(b)
    ws, we = to_utc(local_date, lo, zone), to_utc(local_date, hi, zone)
    if we <= ws:
        # `time` comparison ignores `fold`, so this asks only whether the two *clock
        # readings* run forwards — which is the question worth asking here, the instants
        # having already been shown not to. Stripping `fold` says so out loud.
        clock_ordered = hi.replace(fold=0) > lo.replace(fold=0)
        skipped = READS_NEVER in (clock_reads(local_date, lo, zone),
                                  clock_reads(local_date, hi, zone))
        if clock_ordered and skipped:
            # Ordered on the clock and empty in real time, with a reading inside the hour
            # a spring-forward skips: no instant on this date corresponds to it. Falling
            # through to "end must be after start" would send the user hunting a typo they
            # did not make.
            raise ValueError(f"'{rng}' spans the hour the clocks skip on {local_date}, "
                             f"so no time passed between those two readings")
        if clock_ordered and lo.fold and not hi.fold:
            # A fall-back day, marked on one end. The start is the second pass and the
            # unmarked end is the first, an hour earlier — the cause is the *end*, so say
            # so rather than blaming the range.
            raise ValueError(
                f"'{rng}' carries the second-pass marker on its start only, so the end "
                f"resolves to the first pass over the hour the clocks repeat on "
                f"{local_date} — an hour before the start. Mark both ends or neither")
        raise ValueError(f"end must be after start in range '{rng}'")
    return ws, we


def utc_bounds(local_date, zone):
    """The local day as the Z-suffixed UTC strings the activity source's events API wants.

    Both ends are resolved in the zone independently, so the day the clocks change is
    asked for at its true length — twenty-five hours in autumn, twenty-three in spring —
    rather than at a flat twenty-four hung off whichever offset was read once.
    """
    start = to_utc(local_date, dt.time(0, 0), zone)
    end = to_utc(local_date + dt.timedelta(days=1), dt.time(0, 0), zone)
    return (start.strftime("%Y-%m-%dT%H:%M:%SZ"), end.strftime("%Y-%m-%dT%H:%M:%SZ"))


def local_clock(moment, zone):
    """An instant as the `HH:MM:SS` a clock in `zone` showed at it.

    No date: a day that runs past midnight renders its end as `01:12:00`, which is the
    established output shape and the one the goldens pin.

    On the hour a fall-back repeats, that shape is not enough on its own — two instants an
    hour apart show the same clock — so the second pass over it is suffixed `*`. An
    hour-long break across the change used to render `02:30:00-02:30:00`, sixty minutes as
    a zero-length string; it now ends `02:30:00*`. The marker is exact rather than
    decorative: `parse_local_time()` reads it back, so a time lifted out of one script's
    output names the same instant when handed to another's `--window` or `--cover`.

    It appears on one hour of one day a year, and never at all for a `--utc-offset` run,
    whose zone is that offset all year and so has no repeated hour to mark.
    """
    local = moment.astimezone(zone)
    return local.strftime("%H:%M:%S") + (SECOND_PASS_MARK if local.fold else "")
