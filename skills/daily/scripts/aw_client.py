"""Shared ActivityWatch REST helpers for the billables `daily` skill.

`afk_blocks.py` reads the day skeleton and `activity_timeline.py` reads its
content, but both talk to the same local AW server the same way: discover a
hostname-suffixed bucket, pull a day of events, collapse the heartbeats. Each
used to carry its own copy of that code, so a fix to one left the other wrong.

It also owns the two facts about *where and when* a day is read — the server's address and
the user's zone — because both scripts need them and neither should answer them its own
way. Both resolve through `skill_config`, so they arrive from wherever the user configured
them and nothing here knows about the harness.

No third-party deps - stdlib urllib, like the sibling harvest_*.py helpers.
"""
import datetime as dt
import json
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import skill_config

DEFAULT_ACTIVITY_URL = "http://localhost:5600"


def resolve_base() -> str:
    """The `/api/0` prefix every request is built on, from `TIMESHEET_ACTIVITY_URL`.

    Optional, and its default is the answer for almost everyone: ActivityWatch runs on the
    machine you are typing on. It is declared configuration rather than a constant for the
    case it isn't — a second machine, a non-standard port — which used to mean editing an
    installed script that the next update overwrites.
    """
    base = skill_config.setting("TIMESHEET_ACTIVITY_URL", default=DEFAULT_ACTIVITY_URL)
    return base.rstrip("/") + "/api/0"


AW_BASE = resolve_base()


def resolve_zone(flag):
    """The timezone this day's local clock is read in.

    `flag` is whatever `--utc-offset` supplied, or None; it wins, so a day spent in
    another zone can still be reconstructed without reconfiguring anything. It resolves to
    a zone that is that offset all year, which is what passing a number has always meant.
    Otherwise the configured `TIMESHEET_TIMEZONE` is loaded.

    A zone rather than a number, because a day does not necessarily have *one* offset.
    This used to answer with a single figure read at local noon, and on the day the clocks
    change that is wrong at both ends of the day at once: the fetch window opens an hour
    late or early, and every event on the far side of the transition renders an hour out.
    Neither failure raises anything — the day simply reads short and starts in the wrong
    place. Handing the zone itself to the arithmetic below lets each instant be converted
    at the offset in force for *it*.

    There is deliberately no fallback. This used to be `default=12.0` in both scripts'
    argument parsers, so every user who was not in New Zealand got a day boundary up to
    twelve hours out — and, again, nothing failed. No offset is safe to guess, so an
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
            "No timezone configured, and no --utc-offset given.\n"
            "  A day's boundaries depend on your zone, so there is nothing safe to assume.\n"
            "  Set it once:  /plugin configure billables  -> TIMESHEET_TIMEZONE\n"
            "                (an IANA name, e.g. Europe/London or Pacific/Auckland)\n"
            "  Already set it? Start a new session — the value is published at session\n"
            "  start. If a new session still shows this, see references/setup.md\n"
            "  § 'When the configuration does not arrive'.\n"
            "  Or for this run only:  --utc-offset <hours>")
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        skill_config.fail_missing(
            f"Could not load the timezone '{name}' ({exc}).\n"
            "  Check it against the IANA list (e.g. Europe/London, Pacific/Auckland).\n"
            "  On Windows the zone database is a separate install:  pip install tzdata\n"
            "  Or bypass it for this run:  --utc-offset <hours>")


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


def get(path):
    try:
        with urllib.request.urlopen(AW_BASE + path, timeout=15) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        # An HTTPError never reaches the `with`, so its response body is left open. That
        # matters most for the settings endpoint, whose absence load_classes() swallows
        # by design — nothing downstream ever sees the object to close it.
        e.close()
        raise


def pick_bucket(buckets, prefix):
    """Bucket id starting with `prefix`, or None. Prefers a hostname-suffixed match
    over an unsuffixed leftover; among suffixed candidates, breaks ties by
    `last_updated` so a stale post-reimage bucket loses to the actively-reporting
    host. Takes an already-fetched `{bucket_id: {...}}` listing (as returned by
    `GET /buckets/`) so a caller wanting several buckets pays for one such call
    rather than one per prefix."""
    cands = [b for b in buckets if b.startswith(prefix)]
    if not cands:
        return None
    return max(cands, key=lambda b: ("_" in b, buckets[b].get("last_updated") or ""))


def fetch_events(bucket, start_utc, end_utc):
    """Events in the range. `bucket` may be None: the web watchers are optional, so
    discovery legitimately finds nothing for them."""
    if not bucket:
        return []
    return get(f"/buckets/{bucket}/events?start={start_utc}&end={end_utc}&limit=10000")


def dedupe_heartbeats(events):
    """AW extends an ongoing event by re-emitting it with the same timestamp and a
    longer duration. Keep the longest duration per timestamp so we don't double-count."""
    best = {}
    for e in events:
        ts = e["timestamp"]
        if ts not in best or e["duration"] > best[ts]["duration"]:
            best[ts] = e
    return sorted(best.values(), key=lambda e: e["timestamp"])


def parse_ts(ts):
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))


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


def parse_range(rng, local_date, zone):
    """Parse a local 'HH:MM-HH:MM' (seconds optional) to an aware UTC (start, end) pair.

    Raises ValueError on a bad format or a reversed/empty range. Shared because both
    scripts take a `--window` in this shape and each used to parse it its own way: the
    afk one rejected `17:00-09:00`, the timeline one accepted it and printed an empty
    result, so the same typo produced an error in one script and a plausible-looking
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
    """The local day as the Z-suffixed UTC strings the AW events API wants.

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
