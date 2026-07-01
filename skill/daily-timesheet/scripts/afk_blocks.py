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
NOISE_FLOOR = 5           # drop sub-5s events (tab-switch noise), per SKILL.md


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

    # Build canonical spans from deduped afk stream.
    spans = []  # (start_dt, end_dt, status, dur_s)
    for e in afk_events:
        s = parse_ts(e["timestamp"])
        spans.append((s, s + dt.timedelta(seconds=e["duration"]), e["data"].get("status"), e["duration"]))

    not_afk = [s for s in spans if s[2] == "not-afk"]
    if not not_afk:
        print(f"No not-afk activity found for {args.date}.")
        return 0

    work_start = not_afk[0][0]
    work_end = max(s[1] for s in not_afk)  # last moment of genuine activity = end of day

    # Breaks: afk spans >= threshold that fall *within* the workday. The big afk
    # spans before work_start and after work_end aren't breaks — they're just
    # "not at work yet / done for the day" — so exclude them.
    breaks = [(s[0], s[1], s[3]) for s in spans
              if s[2] == "afk" and s[3] >= args.afk_threshold
              and s[0] >= work_start and s[1] <= work_end]

    # Active spans: walk chronologically, fold short afk in, split on long afk.
    active_spans = []
    cur_start = cur_end = None
    for s, e, status, dur in spans:
        if status == "not-afk":
            if cur_start is None:
                cur_start, cur_end = s, e
            else:
                cur_end = max(cur_end, e)
        elif dur >= args.afk_threshold:
            if cur_start is not None:
                active_spans.append((cur_start, cur_end))
                cur_start = cur_end = None
        # short afk: fold in (do nothing — next not-afk extends the span)
    if cur_start is not None:
        active_spans.append((cur_start, cur_end))

    total_active_s = sum(s[3] for s in not_afk)

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
            a, b = args.window.split("-", 1)
            ws = (dt.datetime.combine(local_date, dt.datetime.strptime(a.strip(), "%H:%M").time())
                  - offset).replace(tzinfo=dt.timezone.utc)
            we = (dt.datetime.combine(local_date, dt.datetime.strptime(b.strip(), "%H:%M").time())
                  - offset).replace(tzinfo=dt.timezone.utc)
        except Exception:
            print(f"ERR bad --window '{args.window}', expected HH:MM-HH:MM", file=sys.stderr)
            return 2
        win_dur = (we - ws).total_seconds()
        overlap = 0.0
        for s, e, status, dur in spans:
            if status != "not-afk":
                continue
            lo, hi = max(s, ws), min(e, we)
            if hi > lo:
                overlap += (hi - lo).total_seconds()
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
                a, b = part.split("-", 1)
                cs = (dt.datetime.combine(local_date, dt.datetime.strptime(a.strip(), "%H:%M").time())
                      - offset).replace(tzinfo=dt.timezone.utc)
                ce = (dt.datetime.combine(local_date, dt.datetime.strptime(b.strip(), "%H:%M").time())
                      - offset).replace(tzinfo=dt.timezone.utc)
                prop.append((cs, ce))
        except Exception:
            print(f"ERR bad --cover '{args.cover}', expected HH:MM-HH:MM,...", file=sys.stderr)
            return 2

        def active_min(lo, hi):
            tot = 0.0
            for s, e, status, dur in spans:
                if status != "not-afk":
                    continue
                a2, b2 = max(s, lo), min(e, hi)
                if b2 > a2:
                    tot += (b2 - a2).total_seconds()
            return tot / 60.0

        # Detected breaks (>= threshold) split active_spans, so they never fall *inside*
        # one — subtracting only the proposed blocks already excludes them as expected gaps.
        uncovered = []
        for a_start, a_end in active_spans:
            segments = [(a_start, a_end)]
            for cs, ce in prop:
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
                am = active_min(s0, e0)
                if am >= 15.0:
                    uncovered.append({"start": to_local(s0), "end": to_local(e0),
                                      "active_min": round(am, 1)})
        covered_active = round(sum(active_min(cs, ce) for cs, ce in prop), 1)
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
        "total_active_min": round(total_active_s / 60, 1),
        "breaks": [{"start": to_local(s), "end": to_local(e), "min": round(d / 60, 1)} for s, e, d in breaks],
        "active_spans": [{"start": to_local(s), "end": to_local(e),
                          "min": round((e - s).total_seconds() / 60, 1)} for s, e in active_spans],
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
