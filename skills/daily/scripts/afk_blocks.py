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

from aw_client import (AW_BASE, dedupe_heartbeats, fetch_events, get,
                       local_clock, parse_local_time, parse_range, parse_ts,
                       pick_bucket, resolve_zone, utc_bounds, zone_label)

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


def to_spans(events):
    """Deduped AW events -> spans."""
    spans = []
    for e in events:
        s = parse_ts(e["timestamp"])
        spans.append((s, s + dt.timedelta(seconds=e["duration"]), e["data"].get("status"), e["duration"]))
    return spans


def work_bounds(spans, solid_s=SOLID_S, blip_gap_s=BLIP_GAP_S):
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
            if cur_start is None:
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


def uncovered_segments(spans, active, proposed, min_uncovered_s=MIN_UNCOVERED_S):
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
    except Exception as e:
        print(f"ERR ActivityWatch unreachable at {AW_BASE} ({e})", file=sys.stderr)
        return 1
    if not afk_bucket:
        print("ERR no aw-watcher-afk bucket found", file=sys.stderr)
        return 1

    afk_events = dedupe_heartbeats(fetch_events(afk_bucket, start_utc, end_utc))

    def to_local(d):
        return local_clock(d, zone)

    spans = insert_data_gaps(to_spans(afk_events), args.afk_threshold)
    bounds = work_bounds(spans, args.solid, args.blip_gap)
    if bounds is None:
        # Same key set as a normal result, so `--json` output can be parsed without
        # first sniffing whether the day happened to have any activity in it.
        if args.json:
            print(json.dumps({
                "date": args.date, "afk_bucket": afk_bucket,
                "work_start": None, "work_end": None, "work_end_blip": None,
                "total_active_min": 0.0, "breaks": [], "active_spans": [],
                "window_watcher_tail": None, "window_report": None,
                "coverage_report": None,
            }, indent=2))
        else:
            print(f"No not-afk activity found for {args.date}.")
        return 0

    work_start, work_end = bounds["work_start"], bounds["work_end"]
    last_solid_end, work_end_blip = bounds["last_solid_end"], bounds["blip"]
    total_active_s = total_active_seconds(spans)

    breaks = find_breaks(spans, work_start, work_end, args.afk_threshold)
    active = active_spans(spans, args.afk_threshold)

    # Window-watcher tail: does a foreground window run past work end?
    win_tail = None
    if win_bucket:
        try:
            wev = dedupe_heartbeats(fetch_events(win_bucket, start_utc, end_utc))
            if wev:
                last = max(parse_ts(e["timestamp"]) + dt.timedelta(seconds=e["duration"]) for e in wev)
                gap_min = (last - work_end).total_seconds() / 60
                win_tail = {"end": to_local(last), "gap_past_work_end_min": round(gap_min, 1)}
        except Exception:
            pass

    # Optional active_ratio for a candidate window.
    window_report = None
    if args.window:
        try:
            ws, we = parse_range(args.window, local_date, zone)
        except Exception as e:
            print(f"ERR bad --window '{args.window}', expected HH:MM-HH:MM (seconds optional): {e}",
                  file=sys.stderr)
            return 2
        win_dur = (we - ws).total_seconds()
        overlap = active_seconds(spans, ws, we)
        ratio = overlap / win_dur if win_dur > 0 else 0.0
        hi, lo = args.active_band, args.thin_band
        band = (f"active (>={hi:g})" if ratio >= hi
                else (f"thin ({lo:g}-{hi:g})" if ratio >= lo else f"mostly idle (<{lo:g})"))
        window_report = {
            "window": args.window,
            "active_ratio": round(ratio, 2),
            "active_min": round(overlap / 60, 1),
            "window_min": round(win_dur / 60, 1),
            "verdict": band,
        }

    # Coverage check: do the proposed billable blocks cover the AFK active_spans?
    # The symmetric partner to the work_end ceiling — surfaces UNDER-billing (active
    # time silently dropped) the way win_tail surfaces over-billing past end-of-day.
    coverage_report = None
    if args.cover:
        prop = []
        try:
            for part in args.cover.split(","):
                part = part.strip()
                if not part:
                    continue
                prop.append(parse_range(part, local_date, zone))
        except Exception as e:
            print(f"ERR bad --cover '{args.cover}', expected HH:MM-HH:MM,... (seconds optional): {e}",
                  file=sys.stderr)
            return 2

        uncovered = [{"start": to_local(s0), "end": to_local(e0), "active_min": round(secs / 60, 1)}
                     for s0, e0, secs in uncovered_segments(spans, active, prop,
                                                            args.min_uncovered)]
        # Union the proposed blocks before totalling. Summing them independently let two
        # overlapping blocks report more covered activity than the day held — and a
        # coverage figure above 100% reads as "nothing was missed" at exactly the moment
        # the proposed blocks are malformed.
        merged = []
        for cs, ce in sorted(prop):
            if merged and cs <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], ce))
            else:
                merged.append((cs, ce))
        covered_active = round(sum(active_seconds(spans, cs, ce) for cs, ce in merged) / 60, 1)
        coverage_report = {
            "proposed_blocks": args.cover,
            "covered_active_min": covered_active,
            "total_active_min": round(total_active_s / 60, 1),
            "uncovered": uncovered,
        }

    result = {
        "date": args.date,
        "afk_bucket": afk_bucket,
        "work_start": to_local(work_start),
        "work_end": to_local(work_end),
        "work_end_blip": ({"last_solid_end": to_local(last_solid_end)} if work_end_blip else None),
        "total_active_min": round(total_active_s / 60, 1),
        "breaks": [{"start": to_local(s), "end": to_local(e), "min": round(d / 60, 1),
                    "kind": break_kind(spans, s, e)} for s, e, d in breaks],
        "active_spans": [{"start": to_local(s), "end": to_local(e),
                          "min": round((e - s).total_seconds() / 60, 1)} for s, e in active],
        "window_watcher_tail": win_tail,
        "window_report": window_report,
        "coverage_report": coverage_report,
    }

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    # --cover wants the whole skeleton; a bare --window does not.
    focused = bool(args.window) and not args.cover

    print(f"AFK analysis for {args.date}  ({zone_label(zone)}, break>={args.afk_threshold}s)")
    print(f"  bucket:      {afk_bucket}")
    print(f"  work start:  {result['work_start']}")
    print(f"  WORK END:    {result['work_end']}   <- end of day; do not bill past this")
    if work_end_blip:
        print(f"  BLIP:        work_end is a momentary flicker; last substantive activity "
              f"ended {result['work_end_blip']['last_solid_end']} -> end the final block there")
    print(f"  active time: {result['total_active_min']} min total")
    if win_tail:
        flag = "  <- left-in-focus trap, NOT work" if win_tail["gap_past_work_end_min"] > 1 else ""
        print(f"  window tail: last window event ends {win_tail['end']} "
              f"({win_tail['gap_past_work_end_min']:+g} min vs work end){flag}")
    # A --window probe is a focused question ("what is the ratio for 15:58-16:25?").
    # Reprinting the full skeleton for it means a run that checks four thin stretches
    # pays for four whole-day dumps it already has. Keep the day's ceiling (work_end,
    # blip and tail flags stay above) and drop the two lists.
    if not focused:
        print(f"  breaks (>= {args.afk_threshold//60} min):")
        if breaks:
            for b in result["breaks"]:
                tag = ("   <- no AFK data (machine asleep/locked), not a recorded idle span"
                       if b["kind"] == GAP_STATUS else "")
                print(f"     {b['start']} - {b['end']}  ({b['min']} min){tag}")
        else:
            print("     (none)")
        print(f"  active spans (short afk folded in):")
        for s in result["active_spans"]:
            print(f"     {s['start']} - {s['end']}  ({s['min']} min)")
    if window_report:
        w = window_report
        print(f"  active_ratio for {w['window']}: {w['active_ratio']} "
              f"({w['active_min']}/{w['window_min']} min) -> {w['verdict']}")
    if coverage_report:
        c = coverage_report
        print(f"  coverage of proposed blocks vs AFK active_spans:")
        print(f"     blocks cover {c['covered_active_min']} of {c['total_active_min']} active min")
        if c["uncovered"]:
            for u in c["uncovered"]:
                print(f"     UNCOVERED active {u['start']} - {u['end']}  "
                      f"({u['active_min']} active min)  <- not billed, not a break")
        else:
            print(f"     (all active spans covered)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
