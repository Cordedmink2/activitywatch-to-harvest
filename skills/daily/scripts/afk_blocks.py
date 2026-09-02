"""Deterministic AFK-watcher analyzer for the billables `daily` skill.

The skill's Step 3 needs a few facts that are easy to get *wrong* by eyeballing
raw ActivityWatch JSON: where the day genuinely ends, where the real breaks are,
and how "active" a candidate block actually is. The classic failure is trusting
the *window* watcher — a terminal / IDE / LockApp window can sit in the
foreground for ages after the user has walked away, so its event duration looks
like work but isn't. The AFK watcher is the authoritative activity signal; this
script reduces it to clean numbers so the model can classify instead of doing
timestamp arithmetic in its head.

What it computes (all times rendered in the user's local zone):
  - work start / work end  -> first and LAST `not-afk` moment of the day. Work
    end is the true end-of-day; never bill past it.
  - breaks                 -> `afk` spans >= the break threshold (default 1050s).
  - active spans           -> contiguous `not-afk` runs, short afk folded in.
  - total active minutes.
  - window-watcher tail     -> end of the last window event, flagged when it runs
    past work end (that gap is the left-in-focus trap, not real work).
  - active_ratio for an arbitrary --window HH:MM-HH:MM (the Step 3 validation).

No third-party deps — stdlib urllib, via the shared aw_client.py.

Usage:
  python scripts/afk_blocks.py 2026-05-28
  python scripts/afk_blocks.py 2026-05-28 --window 18:45-20:00
  python scripts/afk_blocks.py 2026-05-28 --json
  python scripts/afk_blocks.py 2026-05-28 --utc-offset 13   # this run only

The day's boundaries come from the configured TIMESHEET_TIMEZONE, converted at
each instant rather than once for the day, so the day the clocks change is read
at its true length and needs nothing from the user. --utc-offset overrides it
for one run. There is no assumed zone: see aw_client.resolve_zone for why.

The judgement constants below (--solid, --blip-gap, --min-uncovered, the two
bands) are defaults, not policy. They are a person's working style, so they
belong in the user's workspace `context.md` § Preferences, from where the model
passes them here.
"""
import argparse
import datetime as dt
import json
import sys
from typing import NamedTuple

from aw_client import (UsageError, dedupe_heartbeats, fetch_events, get, local_clock,
                       parse_range, parse_ts, pick_bucket, resolve_base, resolve_zone,
                       utc_bounds, zone_label)

DEFAULT_THRESHOLD = 1050  # 17.5 min — the skill's "real break" boundary


def discover_buckets():
    """Return (afk_bucket, window_bucket) from one bucket listing."""
    # Prefixes deliberately carry no trailing `_`: pick_bucket prefers a hostname-suffixed
    # bucket over an unsuffixed one, and a prefix ending in `_` made every unsuffixed
    # bucket invisible — so that preference could never fire, and an AW instance that
    # does not suffix its buckets looked to this script like an AW with no watchers.
    buckets = get("/buckets/")
    return pick_bucket(buckets, "aw-watcher-afk"), pick_bucket(buckets, "aw-watcher-window")


# -- Day arithmetic. Pure functions over spans, so they're testable without AW. --
# A span is (start, end, status, duration_s); `spans` is always chronological.

# Defaults for the judgement calls, each exposed as a flag in main(). They are one
# person's working rhythm, not facts about ActivityWatch, so they are overridable.
SOLID_S = 120       # shorter not-afk runs don't count as substantive activity
BLIP_GAP_S = 600    # gap after the last substantive activity that makes work_end a flicker
MIN_UNCOVERED_S = 900
ACTIVE_BAND = 0.7   # active_ratio at or above which a window reads as billable
THIN_BAND = 0.4     # ...and below which it reads as mostly idle


class Tunables(NamedTuple):
    """The judgement calls, as one value: what `main()` reads off its flags and hands to
    `day_skeleton()`, and what a test passes without a command line. The defaults are the
    constants above, so a test that says nothing gets the shipped behaviour."""
    afk_threshold: int = DEFAULT_THRESHOLD
    solid: float = SOLID_S
    blip_gap: float = BLIP_GAP_S
    min_uncovered: float = MIN_UNCOVERED_S
    active_band: float = ACTIVE_BAND
    thin_band: float = THIN_BAND


def to_spans(events):
    """Deduped AW events -> spans."""
    spans = []
    for e in events:
        s = parse_ts(e["timestamp"])
        spans.append((s, s + dt.timedelta(seconds=e["duration"]), e["data"].get("status"), e["duration"]))
    return spans


def work_bounds(spans, solid_s: float = SOLID_S, blip_gap_s: float = BLIP_GAP_S):
    """First and last not-afk moment, with the end-of-day blip guard.

    `blip` means work_end came from a momentary flicker (mouse nudge, auto-wake)
    long after the last substantive activity, so the final block shouldn't be
    stretched to it. Returns None for a day with no not-afk activity at all.
    """
    not_afk = [s for s in spans if s[2] == "not-afk"]
    if not not_afk:
        return None
    work_end = max(s[1] for s in not_afk)
    last_solid_end = max((s[1] for s in not_afk if s[3] >= solid_s), default=work_end)
    return {
        "work_start": min(s[0] for s in not_afk),
        "work_end": work_end,
        "last_solid_end": last_solid_end,
        "blip": (work_end - last_solid_end).total_seconds() >= blip_gap_s,
    }


def total_active_seconds(spans):
    """Whole-day not-afk time."""
    return sum(dur for _, _, status, dur in spans if status == "not-afk")


GAP_STATUS = "gap"   # a hole in the AFK record: watcher stopped (machine slept/locked)


def insert_data_gaps(spans, threshold_s):
    """Materialise holes in the AFK record as explicit spans.

    The watcher writes nothing at all while the machine sleeps or is locked, so a long
    absence leaves a HOLE between two events rather than an `afk` event. find_breaks()
    only looks at recorded `afk` spans and active_spans() only splits on one, so an
    unmaterialised hole is invisible to the first and merged straight across by the
    second - a real break vanishes and the day reads as one unbroken run."""
    out = []
    for span in spans:
        if out:
            prev_end = out[-1][1]
            hole = (span[0] - prev_end).total_seconds()
            if hole >= threshold_s:
                out.append((prev_end, span[0], GAP_STATUS, hole))
        out.append(span)
    return out


def find_breaks(spans, work_start, work_end, threshold_s):
    """afk spans >= threshold falling within the workday. The big afk spans either
    side of it aren't breaks - they're not being at work yet, and being done."""
    return [(s, e, dur) for s, e, status, dur in spans
            if status in ("afk", GAP_STATUS) and dur >= threshold_s
            and s >= work_start and e <= work_end]


def break_kind(spans, start, end):
    """Which sort of break this is: "gap" = a hole in the AFK record (watcher stopped,
    machine slept or locked), "afk" = a recorded idle span with the user still at the
    desk. Only the second is positive evidence of anything."""
    for s, e, status, _ in spans:
        if s == start and e == end and status == GAP_STATUS:
            return GAP_STATUS
    return "afk"


def active_spans(spans, threshold_s):
    """Contiguous not-afk runs: short afk folded in, afk >= threshold splits the run."""
    out = []
    cur_start = cur_end = None
    for s, e, status, dur in spans:
        if status == "not-afk":
            if cur_end is None:      # set with cur_start, so either one answers "no run open"
                cur_start, cur_end = s, e
            else:
                cur_end = max(cur_end, e)
        elif dur >= threshold_s and cur_start is not None:
            out.append((cur_start, cur_end))
            cur_start = cur_end = None
    if cur_start is not None:
        out.append((cur_start, cur_end))
    return out


def active_seconds(spans, lo, hi):
    """not-afk seconds between lo and hi."""
    total = 0.0
    for s, e, status, dur in spans:
        if status != "not-afk":
            continue
        a, b = max(s, lo), min(e, hi)
        if b > a:
            total += (b - a).total_seconds()
    return total


def uncovered_segments(spans, active, proposed, min_uncovered_s: float = MIN_UNCOVERED_S):
    """Active time the proposed billable blocks leave out - the under-billing check,
    symmetric to the work_end ceiling that catches over-billing. Segments holding
    less than `min_uncovered_s` of activity are block rounding, not missed work.

    Detected breaks already split `active`, so they never fall inside one of its
    spans - subtracting the proposed blocks alone can't report a break as a miss.
    """
    gaps = []
    for a_start, a_end in active:
        segments = [(a_start, a_end)]
        for cs, ce in proposed:
            nxt = []
            for s0, e0 in segments:
                if ce <= s0 or cs >= e0:   # no overlap: segment survives whole
                    nxt.append((s0, e0))
                    continue
                if cs > s0:                # keep the part before the block
                    nxt.append((s0, cs))
                if ce < e0:                # keep the part after it
                    nxt.append((ce, e0))
            segments = nxt
        for s0, e0 in segments:
            secs = active_seconds(spans, s0, e0)
            if secs >= min_uncovered_s:
                gaps.append((s0, e0, secs))
    return gaps


def union_ranges(ranges):
    """Merge overlapping or touching `(start, end)` pairs into disjoint ones, in order.

    Summing the proposed blocks independently let two overlapping blocks report more
    covered activity than the day held — and a coverage figure above 100% reads as
    "nothing was missed" at exactly the moment the proposed blocks are malformed.
    """
    merged = []
    for cs, ce in sorted(ranges):
        if merged and cs <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], ce))
        else:
            merged.append((cs, ce))
    return merged


def band_verdict(ratio, active_band=ACTIVE_BAND, thin_band=THIN_BAND):
    """The word the model bills on, with the band it fell in spelled out beside it."""
    hi, lo = active_band, thin_band
    if ratio >= hi:
        return f"active (>={hi:g})"
    if ratio >= lo:
        return f"thin ({lo:g}-{hi:g})"
    return f"mostly idle (<{lo:g})"


def window_watcher_tail(win_events, work_end, zone):
    """Where the last foreground window event ended, against the AFK work end.

    A terminal, IDE or lock screen can sit in the foreground long after the user has
    walked away; a tail that runs past work end is that trap, not work. None when the
    window watcher recorded nothing for the day.
    """
    if not win_events:
        return None
    last = max(parse_ts(e["timestamp"]) + dt.timedelta(seconds=e["duration"]) for e in win_events)
    gap_min = (last - work_end).total_seconds() / 60
    return {"end": local_clock(last, zone), "gap_past_work_end_min": round(gap_min, 1)}


def window_report(spans, label, ws, we, tunables=Tunables()):
    """`active_ratio` for one candidate window — the Step 3 validation of a block."""
    win_dur = (we - ws).total_seconds()
    overlap = active_seconds(spans, ws, we)
    ratio = overlap / win_dur if win_dur > 0 else 0.0
    return {
        "window": label,
        "active_ratio": round(ratio, 2),
        "active_min": round(overlap / 60, 1),
        "window_min": round(win_dur / 60, 1),
        "verdict": band_verdict(ratio, tunables.active_band, tunables.thin_band),
    }


def coverage_report(spans, active, label, proposed, zone, tunables=Tunables()):
    """Do the proposed billable blocks cover the AFK active spans?

    The symmetric partner to the work_end ceiling — surfaces UNDER-billing (active time
    silently dropped) the way the window-watcher tail surfaces over-billing past the end
    of the day. The blocks are unioned before totalling; `union_ranges` says why.
    """
    uncovered = [{"start": local_clock(s0, zone), "end": local_clock(e0, zone),
                  "active_min": round(secs / 60, 1)}
                 for s0, e0, secs in uncovered_segments(spans, active, proposed,
                                                        tunables.min_uncovered)]
    covered = sum(active_seconds(spans, cs, ce) for cs, ce in union_ranges(proposed))
    return {
        "proposed_blocks": label,
        "covered_active_min": round(covered / 60, 1),
        "total_active_min": round(total_active_seconds(spans) / 60, 1),
        "uncovered": uncovered,
    }


def empty_skeleton(date, afk_bucket):
    """The result's one shape, with nothing in it: every key a populated day has, so
    `--json` output parses the same way whether or not the day held any activity. The
    populated day is this dict filled in, never a second literal."""
    return {
        "date": date.isoformat(), "afk_bucket": afk_bucket,
        "work_start": None, "work_end": None, "work_end_blip": None,
        "total_active_min": 0.0, "breaks": [], "active_spans": [],
        "window_watcher_tail": None, "window_report": None, "coverage_report": None,
    }


def _parse_window(label, local_date, zone):
    """One `HH:MM-HH:MM`, or a `UsageError` naming the flag and what it expected."""
    try:
        return parse_range(label, local_date, zone)
    except Exception as e:
        raise UsageError(f"bad --window '{label}', expected HH:MM-HH:MM "
                         f"(seconds optional): {e}") from e


def _parse_cover(label, local_date, zone):
    """Every `HH:MM-HH:MM` in the comma-separated `--cover` value, empty parts skipped."""
    try:
        return [parse_range(part.strip(), local_date, zone)
                for part in label.split(",") if part.strip()]
    except Exception as e:
        raise UsageError(f"bad --cover '{label}', expected HH:MM-HH:MM,... "
                         f"(seconds optional): {e}") from e


def day_skeleton(afk_events, win_events, date, zone, afk_bucket=None,
                 tunables=Tunables(), window=None, cover=None):
    """The day, reduced to the facts the skill bills against — from events, printing nothing.

    `afk_events` and `win_events` are the deduplicated streams for the day; `window` and
    `cover` are the raw flag values, read here so that an unreadable one on a day with
    no activity is still answered by the empty skeleton, as it always was. Both
    renderings in `main()` run over what this returns, so the JSON a test reads and the
    text the model reads cannot disagree about the day.
    """
    result = empty_skeleton(date, afk_bucket)
    spans = insert_data_gaps(to_spans(afk_events), tunables.afk_threshold)
    bounds = work_bounds(spans, tunables.solid, tunables.blip_gap)
    if bounds is None:
        return result

    work_start, work_end = bounds["work_start"], bounds["work_end"]
    breaks = find_breaks(spans, work_start, work_end, tunables.afk_threshold)
    active = active_spans(spans, tunables.afk_threshold)

    report = None
    if window:
        ws, we = _parse_window(window, date, zone)
        report = window_report(spans, window, ws, we, tunables)
    coverage = None
    if cover:
        proposed = _parse_cover(cover, date, zone)
        coverage = coverage_report(spans, active, cover, proposed, zone, tunables)

    filled = {
        "work_start": local_clock(work_start, zone),
        "work_end": local_clock(work_end, zone),
        "work_end_blip": ({"last_solid_end": local_clock(bounds["last_solid_end"], zone)}
                          if bounds["blip"] else None),
        "total_active_min": round(total_active_seconds(spans) / 60, 1),
        "breaks": [{"start": local_clock(s, zone), "end": local_clock(e, zone),
                    "min": round(d / 60, 1), "kind": break_kind(spans, s, e)}
                   for s, e, d in breaks],
        "active_spans": [{"start": local_clock(s, zone), "end": local_clock(e, zone),
                          "min": round((e - s).total_seconds() / 60, 1)} for s, e in active],
        "window_watcher_tail": window_watcher_tail(win_events, work_end, zone),
        "window_report": report,
        "coverage_report": coverage,
    }
    result.update(filled)
    return result


def render_text(result, zone, tunables=Tunables(), focused=False):
    """The text rendering of a skeleton, as lines. `focused` is a bare `--window` probe:
    a run that checks four thin stretches should not pay for four whole-day dumps it
    already has, so the day's ceiling stays and the two lists go."""
    out = [f"AFK analysis for {result['date']}  ({zone_label(zone)}, "
           f"break>={tunables.afk_threshold}s)",
           f"  bucket:      {result['afk_bucket']}",
           f"  work start:  {result['work_start']}",
           f"  WORK END:    {result['work_end']}   <- end of day; do not bill past this"]
    if result["work_end_blip"]:
        out.append(f"  BLIP:        work_end is a momentary flicker; last substantive activity "
                   f"ended {result['work_end_blip']['last_solid_end']} -> end the final block there")
    out.append(f"  active time: {result['total_active_min']} min total")
    tail = result["window_watcher_tail"]
    if tail:
        flag = "  <- left-in-focus trap, NOT work" if tail["gap_past_work_end_min"] > 1 else ""
        out.append(f"  window tail: last window event ends {tail['end']} "
                   f"({tail['gap_past_work_end_min']:+g} min vs work end){flag}")
    if not focused:
        out.append(f"  breaks (>= {tunables.afk_threshold//60} min):")
        if result["breaks"]:
            for b in result["breaks"]:
                tag = ("   <- no AFK data (machine asleep/locked), not a recorded idle span"
                       if b["kind"] == GAP_STATUS else "")
                out.append(f"     {b['start']} - {b['end']}  ({b['min']} min){tag}")
        else:
            out.append("     (none)")
        out.append(f"  active spans (short afk folded in):")
        for s in result["active_spans"]:
            out.append(f"     {s['start']} - {s['end']}  ({s['min']} min)")
    if result["window_report"]:
        w = result["window_report"]
        out.append(f"  active_ratio for {w['window']}: {w['active_ratio']} "
                   f"({w['active_min']}/{w['window_min']} min) -> {w['verdict']}")
    if result["coverage_report"]:
        c = result["coverage_report"]
        out.append(f"  coverage of proposed blocks vs AFK active_spans:")
        out.append(f"     blocks cover {c['covered_active_min']} of {c['total_active_min']} active min")
        if c["uncovered"]:
            for u in c["uncovered"]:
                out.append(f"     UNCOVERED active {u['start']} - {u['end']}  "
                           f"({u['active_min']} active min)  <- not billed, not a break")
        else:
            out.append(f"     (all active spans covered)")
    return out


def main():
    ap = argparse.ArgumentParser(description="Analyze AW AFK watcher for one day.")
    ap.add_argument("date", help="YYYY-MM-DD (local date)")
    ap.add_argument("--utc-offset", type=float, default=None,
                    help="Local zone offset from UTC in hours, for this run only. "
                         "Omit to use the configured TIMESHEET_TIMEZONE.")
    ap.add_argument("--afk-threshold", type=int, default=DEFAULT_THRESHOLD,
                    help="Seconds of afk that counts as a real break (default 1050 = 17.5 min)")
    ap.add_argument("--solid", type=float, default=SOLID_S,
                    help=f"Seconds a not-afk run must reach to count as substantive "
                         f"activity rather than a flicker (default {SOLID_S})")
    ap.add_argument("--blip-gap", type=float, default=BLIP_GAP_S,
                    help=f"Seconds between the last substantive activity and work_end "
                         f"that make work_end a blip (default {BLIP_GAP_S})")
    ap.add_argument("--min-uncovered", type=float, default=MIN_UNCOVERED_S,
                    help=f"Smallest uncovered stretch --cover reports as missed work "
                         f"rather than block rounding, in seconds (default {MIN_UNCOVERED_S})")
    ap.add_argument("--active-band", type=float, default=ACTIVE_BAND,
                    help=f"active_ratio at or above which a --window reads as active "
                         f"(default {ACTIVE_BAND})")
    ap.add_argument("--thin-band", type=float, default=THIN_BAND,
                    help=f"active_ratio below which a --window reads as mostly idle "
                         f"(default {THIN_BAND})")
    ap.add_argument("--window", help="Compute active_ratio for HH:MM-HH:MM (local)")
    ap.add_argument("--cover", help="Comma-separated proposed billable blocks "
                    "(HH:MM-HH:MM,HH:MM-HH:MM,...); reports active time they fail to cover")
    ap.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    args = ap.parse_args()

    try:
        local_date = dt.datetime.strptime(args.date, "%Y-%m-%d").date()
    except ValueError:
        print(f"ERR bad date '{args.date}', expected YYYY-MM-DD", file=sys.stderr)
        return 2

    if args.thin_band > args.active_band:
        # Inverted bands don't fail, they produce a verdict string nobody can act on —
        # "thin (0.9-0.5)" — and the model bills on that verdict.
        print(f"ERR --thin-band ({args.thin_band:g}) is above --active-band "
              f"({args.active_band:g}); the bands would read backwards", file=sys.stderr)
        return 2

    # After the date parse, because resolving a zone for an unparseable date would report
    # the configuration problem in front of the typo that is actually in the way.
    zone = resolve_zone(args.utc_offset)

    start_utc, end_utc = utc_bounds(local_date, zone)

    try:
        afk_bucket, win_bucket = discover_buckets()
        if not afk_bucket:
            print("ERR no aw-watcher-afk bucket found", file=sys.stderr)
            return 1
        afk_events = dedupe_heartbeats(fetch_events(afk_bucket, start_utc, end_utc))
        # A missing window bucket is answered with nothing by `fetch_events`, so a day
        # with no window watcher has no tail. A fetch that fails is a fetch that fails,
        # reported like any other, rather than a tail quietly missing from the report.
        win_events = dedupe_heartbeats(fetch_events(win_bucket, start_utc, end_utc))
    except Exception as e:
        print(f"ERR ActivityWatch unreachable at {resolve_base()} ({e})", file=sys.stderr)
        return 1

    tunables = Tunables(args.afk_threshold, args.solid, args.blip_gap, args.min_uncovered,
                        args.active_band, args.thin_band)
    try:
        result = day_skeleton(afk_events, win_events, local_date, zone, afk_bucket,
                              tunables, window=args.window, cover=args.cover)
    except UsageError as e:
        print(f"ERR {e}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, indent=2))
        return 0
    if result["work_start"] is None:
        print(f"No not-afk activity found for {result['date']}.")
        return 0
    # --cover wants the whole skeleton; a bare --window does not.
    focused = bool(args.window) and not args.cover
    print("\n".join(render_text(result, zone, tunables, focused)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
