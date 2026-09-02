"""Window-activity timeline for the billables `daily` skill, tagged with the
client categories ActivityWatch already knows.

afk_blocks.py gives the day *skeleton* (start/end/breaks). This gives the
*content*: a high-resolution, merged timeline of foreground-window activity,
each span tagged with the AW category (client) whose class-rule it matches.
Spans that match no class are "uncategorized"; spans matching several are
flagged — both are exactly the spans to confirm with --window or a screenshot.

AW category rules are read live from GET /api/0/settings -> "classes", so the
tags mirror what the AW web UI shows (regex on the window app + title). The
rules are *client*-level, not project/ticket-level: they get you to "ACME",
never to "ACM-CR202 vs ACM2232S", and are a first-pass signal only — never
taken as 100% certain.

Two modes:
  * default              -> merged category spans for the whole day + per-category
                            day totals (the "bin rollup").
  * --window HH:MM-HH:MM -> zoom one section AND fold in the web watchers
                            (firefox + chrome) URLs/titles for it.

No third-party deps — stdlib urllib, via the shared aw_client.py.

Usage:
  python scripts/activity_timeline.py 2026-06-19
  python scripts/activity_timeline.py 2026-06-19 --window 12:30-14:00
  python scripts/activity_timeline.py 2026-06-19 --json
  python scripts/activity_timeline.py 2026-06-19 --utc-offset 13   # this run only

The day's boundaries come from the configured TIMESHEET_TIMEZONE, converted at
each instant rather than once for the day, so the day the clocks change is read
at its true length. --utc-offset overrides it for one run. There is no assumed
zone — see aw_client.resolve_zone.
"""
import argparse
import datetime as dt
import io
import json
import re
import sys

from aw_client import (dedupe_heartbeats, fetch_events, get, local_clock,
                       parse_range, parse_ts, pick_bucket, resolve_base,
                       resolve_zone, utc_bounds, zone_label)

# Defaults for the two noise constants, each exposed as a flag in main(): what counts as
# noise depends on how a person works, so they belong in the user's `context.md`
# § Preferences rather than only here.
NOISE_FLOOR = 5    # drop sub-5s events (tab-switch noise), per SKILL.md
GAP_FOLD = 60      # inter-event gaps shorter than this don't break a span (seconds)

for _s in (sys.stdout, sys.stderr):   # pytest's captured stdout is not one of these
    if isinstance(_s, io.TextIOWrapper):
        _s.reconfigure(encoding="utf-8")


def load_classes():
    """Return [(label, compiled_regex), ...] from AW settings 'classes'.
    Skips non-regex rules (e.g. parent categories with type 'none')."""
    try:
        settings = get("/settings")
    except Exception:
        return []
    out = []
    for c in settings.get("classes", []):
        rule = c.get("rule") or {}
        if rule.get("type") != "regex":
            continue
        pattern = rule.get("regex")
        if not pattern:
            continue
        flags = re.IGNORECASE if rule.get("ignore_case") else 0
        try:
            rx = re.compile(pattern, flags)
        except re.error:
            continue
        label = ">".join(c.get("name") or []) or pattern
        out.append((label, rx))
    return out


def categorize(app, title, classes):
    """Labels of every class whose regex matches 'app title'. [] if none."""
    hay = f"{app} {title}"
    return [label for label, rx in classes if rx.search(hay)]


def build_window_spans(events, classes, noise_floor=NOISE_FLOOR, gap_fold=GAP_FOLD):
    """Merge chronological window events into spans sharing a category.
    Each span: start, end (datetime), category, multi (bool), categories (set of
    every class label matched within the span), titles {label: secs}."""
    evs = dedupe_heartbeats(events)
    spans = []
    cur = None
    for e in evs:
        if e["duration"] < noise_floor:
            continue
        s = parse_ts(e["timestamp"])
        en = s + dt.timedelta(seconds=e["duration"])
        app = e["data"].get("app", "?")
        title = e["data"].get("title", "") or ""
        cats = categorize(app, title, classes)
        primary = cats[0] if cats else "uncategorized"
        key = f"{app} | {title}"
        if (cur is not None and cur["category"] == primary
                and (s - cur["end"]).total_seconds() < gap_fold):
            cur["end"] = max(cur["end"], en)
            cur["titles"][key] = cur["titles"].get(key, 0) + e["duration"]
            cur["categories"].update(cats)
            cur["multi"] = cur["multi"] or len(cats) > 1
        else:
            if cur is not None:
                spans.append(cur)
            cur = {"start": s, "end": en, "category": primary,
                   "multi": len(cats) > 1, "categories": set(cats),
                   "titles": {key: e["duration"]}}
    if cur is not None:
        spans.append(cur)
    return spans


def category_rollup(events, classes, noise_floor=NOISE_FLOOR):
    """Minutes per category across all deduped events at or above the noise floor."""
    totals = {}
    for e in dedupe_heartbeats(events):
        if e["duration"] < noise_floor:
            continue
        cats = categorize(e["data"].get("app", "?"), e["data"].get("title", "") or "", classes)
        label = cats[0] if cats else "uncategorized"
        totals[label] = totals.get(label, 0) + e["duration"]
    return {k: round(v / 60, 1) for k, v in sorted(totals.items(), key=lambda kv: -kv[1])}


def main():
    ap = argparse.ArgumentParser(description="Categorized window-activity timeline for one day.")
    ap.add_argument("date", help="YYYY-MM-DD (local date)")
    ap.add_argument("--utc-offset", type=float, default=None,
                    help="Local zone offset from UTC in hours, for this run only. "
                         "Omit to use the configured TIMESHEET_TIMEZONE.")
    ap.add_argument("--noise-floor", type=float, default=NOISE_FLOOR,
                    help=f"Drop events shorter than this many seconds as tab-switch noise "
                         f"(default {NOISE_FLOOR})")
    ap.add_argument("--gap-fold", type=float, default=GAP_FOLD,
                    help=f"Inter-event gaps shorter than this many seconds do not break a "
                         f"span (default {GAP_FOLD})")
    ap.add_argument("--window", help="Zoom HH:MM-HH:MM and include web-watcher detail")
    ap.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    ap.add_argument("--full", action="store_true",
                    help="Show every merged span. Default hides sub-threshold spans to save context; "
                         "the per-category rollup still counts them.")
    ap.add_argument("--min-span", type=float, default=3.0,
                    help="Compact (default) text mode hides spans shorter than this many minutes "
                         "(default 3.0); true !MULTI spans are always kept. The per-category rollup "
                         "still counts hidden spans. Ignored with --full or --window.")
    args = ap.parse_args()

    try:
        local_date = dt.datetime.strptime(args.date, "%Y-%m-%d").date()
    except ValueError:
        print(f"ERR bad date '{args.date}', expected YYYY-MM-DD", file=sys.stderr)
        return 2

    # After the date parse: a typo in the date should be reported before a configuration
    # problem the user cannot act on until the date is right anyway.
    zone = resolve_zone(args.utc_offset)

    start_utc, end_utc = utc_bounds(local_date, zone)
    try:
        buckets = get("/buckets/")
        win_bucket = pick_bucket(buckets, "aw-watcher-window")
        win_events = fetch_events(win_bucket, start_utc, end_utc)
    except Exception as e:
        print(f"ERR ActivityWatch unreachable at {resolve_base()} ({e})", file=sys.stderr)
        return 1
    if not win_bucket:
        # Without this, a crashed or renamed window watcher yields a well-formed, totally
        # empty timeline and exit 0 — which reads as "the user did no work" rather than
        # "the instrument is broken". afk_blocks.py already refuses on a missing AFK
        # bucket; silence is the more dangerous answer for both.
        print("ERR no aw-watcher-window bucket found — the window watcher is not "
              "reporting, so this day has no timeline (that is not the same as an empty "
              f"day). Buckets seen: {sorted(buckets) or '(none)'}", file=sys.stderr)
        return 1
    classes = load_classes()

    def to_local(d):
        return local_clock(d, zone)

    spans = build_window_spans(win_events, classes, args.noise_floor, args.gap_fold)
    rollup = category_rollup(win_events, classes, args.noise_floor)

    # Zoom mode: restrict spans + pull web watchers for the window.
    web_rows = None
    if args.window:
        try:
            ws, we = parse_range(args.window, local_date, zone)
        except Exception as e:
            print(f"ERR bad --window '{args.window}', expected HH:MM-HH:MM "
                  f"(seconds optional): {e}", file=sys.stderr)
            return 2
        spans = [s for s in spans if s["end"] > ws and s["start"] < we]
        dated = []
        for pref in ("aw-watcher-web-firefox", "aw-watcher-web-chrome"):
            try:
                b = pick_bucket(buckets, pref)
                for e in dedupe_heartbeats(fetch_events(b, start_utc, end_utc)):
                    if e["duration"] < args.noise_floor:
                        continue
                    t = parse_ts(e["timestamp"])
                    # Overlap, not containment — matching the span filter above. A tab
                    # opened before the zoom and still open inside it is usually the row
                    # that names the client, and keying on the start alone dropped it.
                    if t + dt.timedelta(seconds=e["duration"]) <= ws or t >= we:
                        continue
                    dated.append((t, {"time": to_local(t), "secs": int(e["duration"]),
                                      "title": (e["data"].get("title") or "")[:60],
                                      "url": (e["data"].get("url") or "")[:80]}))
            except Exception:
                pass
        # Sorted on the instant, not on the rendered clock. Inside the hour a fall-back
        # repeats, the two orders disagree: a tab opened at 02:40 on the first pass really
        # does come before one opened at 02:10 on the second, and sorting the strings put
        # the day's browsing in the wrong order for that hour. Two browsers are merged
        # here as well, so this list is never already in order.
        #
        # The instant rides alongside the row rather than inside it: a `datetime` is not
        # JSON-serialisable, and a key added to the payload to be deleted after the sort
        # only has to survive one `return` inserted between the two to reach `json.dumps`.
        dated.sort(key=lambda pair: pair[0])
        web_rows = [row for _, row in dated]

    result = {
        "date": args.date,
        "window_bucket": win_bucket,
        "spans": [{"start": to_local(s["start"]), "end": to_local(s["end"]),
                   "min": round((s["end"] - s["start"]).total_seconds() / 60, 1),
                   "category": s["category"], "multi": s["multi"],
                   "categories": sorted(s["categories"]),
                   "top_titles": sorted(s["titles"].items(), key=lambda kv: -kv[1])[:3]}
                  for s in spans],
        "rollup_min_by_category": rollup,
        "web": web_rows,
    }

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    hdr = f"Window timeline for {args.date} ({zone_label(zone)})"
    if args.window:
        hdr += f"  [zoom {args.window}]"
    print(hdr)
    print(f"  window bucket: {win_bucket}   classes loaded: {len(classes)}")
    # Compact by default: hide spans shorter than min_span (the rollup still counts
    # them) so a day collapses to its substantive blocks. A uniform duration floor —
    # NOT a category filter — because on a thin AW ruleset most real work reads as
    # "uncategorized", so special-casing that category hides nothing. True !MULTI
    # spans (>1 category matched) are always kept. --full or --window show everything.
    show_all = args.full or bool(args.window)
    hidden = 0
    for s in result["spans"]:
        keep = show_all or s["min"] >= args.min_span or s["multi"]
        if not keep:
            hidden += 1
            continue
        flag = " !MULTI" if s["multi"] else ""
        top = s["top_titles"][0][0][:64] if s["top_titles"] else ""
        print(f"  {s['start']}-{s['end']}  {s['min']:>5}m  {s['category']:<14}{flag}  {top}")
    if hidden:
        print(f"  ... {hidden} sub-{args.min_span:g}min spans hidden (still counted in rollup; "
              f"use --full or --window HH:MM-HH:MM to see them)")
    print("  --- day totals by category (min) ---")
    for cat, mins in result["rollup_min_by_category"].items():
        print(f"     {cat:<16} {mins}")
    if web_rows is not None:
        print(f"  --- web tabs in {args.window} (firefox+chrome) ---")
        for r in web_rows:
            print(f"     {r['time']}  [{r['secs']}s] {r['title']} :: {r['url']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
