"""Deterministic AFK-watcher analyzer for the daily-timesheet skill.

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

No third-party deps — stdlib urllib, like the sibling harvest_*.py helpers.

Usage:
  python scripts/afk_blocks.py 2026-05-28
  python scripts/afk_blocks.py 2026-05-28 --window 18:45-20:00
  python scripts/afk_blocks.py 2026-05-28 --json
  python scripts/afk_blocks.py 2026-05-28 --utc-offset 13   # NZDT

Defaults assume NZ (UTC+12). During NZ daylight saving (late Sep - early Apr)
pass --utc-offset 13. The skill's .context.md notes the user's zone.
"""
import argparse
import datetime as dt
import json
import sys
import urllib.request

AW_BASE = "http://localhost:5600/api/0"
DEFAULT_THRESHOLD = 1050  # 17.5 min — the skill's "real break" boundary


def parse_local_time(s):
    """Parse 'HH:MM' or 'HH:MM:SS' to a datetime.time."""
    s = s.strip()
    fmt = "%H:%M:%S" if s.count(":") == 2 else "%H:%M"
    return dt.datetime.strptime(s, fmt).time()


def parse_range(rng, local_date, offset):
    """Parse 'HH:MM-HH:MM' (seconds optional) to an aware UTC (start, end) pair.
    Raises ValueError on bad format or a reversed/empty range."""
    a, b = rng.split("-", 1)
    ws = (dt.datetime.combine(local_date, parse_local_time(a)) - offset).replace(tzinfo=dt.timezone.utc)
    we = (dt.datetime.combine(local_date, parse_local_time(b)) - offset).replace(tzinfo=dt.timezone.utc)
    if we <= ws:
        raise ValueError(f"end must be after start in range '{rng}'")
    return ws, we


def _get(path):
    with urllib.request.urlopen(AW_BASE + path, timeout=15) as r:
        return json.load(r)


def discover_buckets():
    """Return (afk_bucket, window_bucket). Prefer hostname-suffixed live buckets."""
    buckets = _get("/buckets/")
    def pick(prefix):
        cands = [b for b in buckets if b.startswith(prefix)]
        # hostname-suffixed buckets (contain '_') are the live ones
        cands.sort(key=lambda b: ("_" not in b, b))
        return cands[0] if cands else None
    return pick("aw-watcher-afk_"), pick("aw-watcher-window_")


def fetch_events(bucket, start_utc, end_utc):
    q = f"/buckets/{bucket}/events?start={start_utc}&end={end_utc}&limit=10000"
    return _get(q)


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


# -- Day arithmetic. Pure functions over spans, so they're testable without AW. --
# A span is (start, end, status, duration_s); `spans` is always chronological.

SOLID_S = 120       # shorter not-afk runs don't count as substantive activity
BLIP_GAP_S = 600    # gap after the last substantive activity that makes work_end a flicker
MIN_UNCOVERED_S = 900


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
        "total_active_s": sum(s[3] for s in not_afk),
    }


def find_breaks(spans, work_start, work_end, threshold_s):
    """afk spans >= threshold falling within the workday. The big afk spans either
    side of it aren't breaks - they're not being at work yet, and being done."""
    return [(s, e, dur) for s, e, status, dur in spans
            if status == "afk" and dur >= threshold_s and s >= work_start and e <= work_end]


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


def uncovered_segments(spans, active, proposed, min_active_s=MIN_UNCOVERED_S):
    """Active time the proposed billable blocks leave out - the under-billing check,
    symmetric to the work_end ceiling that catches over-billing. Segments holding
    less than min_active_s of activity are block rounding, not missed work.

    Detected breaks already split `active`, so they never fall inside one of its
    spans - subtracting the proposed blocks alone can't report a break as a miss.
    """
    gaps = []
    for a_start, a_end in active:
        segments = [(a_start, a_end)]
        for cs, ce in proposed:
            nxt = []
            for s0, e0 in segments:
                if ce <= s0 or cs >= e0:
                    nxt.append((s0, e0))
                    continue
                if cs > s0:
                    nxt.append((s0, min(cs, e0)))
                if ce < e0:
                    nxt.append((max(ce, s0), e0))
            segments = nxt
        for s0, e0 in segments:
            secs = active_seconds(spans, s0, e0)
            if secs >= min_active_s:
                gaps.append((s0, e0, secs))
    return gaps


def main():
    ap = argparse.ArgumentParser(description="Analyze AW AFK watcher for one day.")
    ap.add_argument("date", help="YYYY-MM-DD (local date)")
    ap.add_argument("--utc-offset", type=float, default=12.0,
                    help="Local zone offset from UTC in hours (default 12 = NZST; use 13 for NZDT)")
    ap.add_argument("--afk-threshold", type=int, default=DEFAULT_THRESHOLD,
                    help="Seconds of afk that counts as a real break (default 1050 = 17.5 min)")
    ap.add_argument("--window", help="Compute active_ratio for HH:MM-HH:MM (local)")
    ap.add_argument("--cover", help="Comma-separated proposed billable blocks "
                    "(HH:MM-HH:MM,HH:MM-HH:MM,...); reports active time they fail to cover")
    ap.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    args = ap.parse_args()

    offset = dt.timedelta(hours=args.utc_offset)
    try:
        local_date = dt.datetime.strptime(args.date, "%Y-%m-%d").date()
    except ValueError:
        print(f"ERR bad date '{args.date}', expected YYYY-MM-DD", file=sys.stderr)
        return 2

    # Local-midnight boundaries -> UTC range.
    local_start = dt.datetime.combine(local_date, dt.time(0, 0))
    start_utc = (local_start - offset).strftime("%Y-%m-%dT%H:%M:%SZ")
    end_utc = (local_start + dt.timedelta(days=1) - offset).strftime("%Y-%m-%dT%H:%M:%SZ")

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
        return (d + offset).strftime("%H:%M:%S")

    spans = to_spans(afk_events)
    bounds = work_bounds(spans)
    if bounds is None:
        print(f"No not-afk activity found for {args.date}.")
        return 0

    work_start, work_end = bounds["work_start"], bounds["work_end"]
    last_solid_end, work_end_blip = bounds["last_solid_end"], bounds["blip"]
    total_active_s = bounds["total_active_s"]

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
            ws, we = parse_range(args.window, local_date, offset)
        except Exception as e:
            print(f"ERR bad --window '{args.window}', expected HH:MM-HH:MM (seconds optional): {e}",
                  file=sys.stderr)
            return 2
        win_dur = (we - ws).total_seconds()
        overlap = active_seconds(spans, ws, we)
        ratio = overlap / win_dur if win_dur > 0 else 0.0
        band = "active (>=0.7)" if ratio >= 0.7 else ("thin (0.4-0.7)" if ratio >= 0.4 else "mostly idle (<0.4)")
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
                prop.append(parse_range(part, local_date, offset))
        except Exception as e:
            print(f"ERR bad --cover '{args.cover}', expected HH:MM-HH:MM,... (seconds optional): {e}",
                  file=sys.stderr)
            return 2

        uncovered = [{"start": to_local(s0), "end": to_local(e0), "active_min": round(secs / 60, 1)}
                     for s0, e0, secs in uncovered_segments(spans, active, prop)]
        covered_active = round(sum(active_seconds(spans, cs, ce) for cs, ce in prop) / 60, 1)
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
        "breaks": [{"start": to_local(s), "end": to_local(e), "min": round(d / 60, 1)} for s, e, d in breaks],
        "active_spans": [{"start": to_local(s), "end": to_local(e),
                          "min": round((e - s).total_seconds() / 60, 1)} for s, e in active],
        "window_watcher_tail": win_tail,
        "window_report": window_report,
        "coverage_report": coverage_report,
    }

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    print(f"AFK analysis for {args.date}  (offset UTC+{args.utc_offset:g}, break>={args.afk_threshold}s)")
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
    print(f"  breaks (>= {args.afk_threshold//60} min):")
    if breaks:
        for b in result["breaks"]:
            print(f"     {b['start']} - {b['end']}  ({b['min']} min)")
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
