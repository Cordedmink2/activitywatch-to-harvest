# daily-timesheet Reliability Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the three points where the daily-timesheet skill forced ad-hoc scripting (window-activity binning, screenshot reading, Harvest task-ID lookup) with bundled, tested tools.

**Architecture:** Three Python scripts in `scripts/` plus a SKILL.md wiring pass. `activity_timeline.py` and `harvest_lookup.py` are new; `screenshot_capture.py` is modified for per-monitor capture. New scripts follow the existing `afk_blocks.py` / `harvest_*.py` conventions (stdlib `urllib`, `argparse` with `--utc-offset`/`--json`, `ERR …` to stderr). Pure logic (categorize, span-merge, catalog search, monitor-ordering) is unit-tested with pytest; live-AW fetch and screen-grab stay thin and out of the tested core.

**Tech Stack:** Python 3.12 stdlib (`urllib`, `argparse`, `re`, `glob`, `json`), Pillow + `mss` (screenshots), pytest (tests), PowerShell (setup script).

**User decisions (already made):**
- Screenshots: "Per-monitor files" — one PNG per monitor, `_mN` suffix.
- Timeline script: "New separate script", "window activity only", "more frequent than 15 mins", "get the client categories from aw" but "don't take this with 100% certainty" — still verifiable via screenshots or "more detail returning aw scripts (for specific sections … can also return web watchers)".
- Granularity: "Both: spans + bin rollup".
- Commit work to the `Cordedmink2/claude-skills` repo (via the claude-skills-repo skill), never the live `.env`.

---

### Task 1: `harvest_lookup.py` — project/task lookup across all catalog pages

**Goal:** A bundled command that finds a Harvest project + its tasks by code or name fragment, searching every `harvest_assignments*.json` page (the pagination that caused the NLS-CR202 miss).

**Files:**
- Create: `scripts/harvest_lookup.py`
- Create: `tests/test_harvest_lookup.py`

**Acceptance Criteria:**
- [ ] `harvest_lookup.py NLS-CR202` (run from the workspace with `.mcp/`) prints project `48084036` and task `Gen - Development/Configuration` id `20753151` marked billable.
- [ ] Searches ALL `harvest_assignments*.json` files, de-duping projects seen on more than one page.
- [ ] Exact-code match sorts first; fragment matches on code OR name also returned.
- [ ] `--task <substr>` filters task rows; `--mcp-dir` overrides the catalog directory; `--json` emits machine-readable output.
- [ ] Exits non-zero with an `ERR`/"No project matching" message to stderr when nothing matches.

**Verify:** `python -m pytest tests/test_harvest_lookup.py -v` → all pass; and `cd <workspace> && python <skill>/scripts/harvest_lookup.py NLS-CR202` → prints the 48084036 row.

**Steps:**

- [ ] **Step 1: Write the failing test**

`tests/test_harvest_lookup.py`:

```python
import json, os, sys, subprocess
import pytest

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts")
sys.path.insert(0, SCRIPTS)
import harvest_lookup as hl


def _write_catalog(mcp_dir):
    # Page 1 holds NLS-CR202; a later page holds a different project + a dupe of NLS-CR202.
    page1 = {"project_assignments": [
        {"project": {"id": 48084036, "code": "NLS-CR202",
                     "name": "CMS Backlog Requirements Implementation Phase 2"},
         "task_assignments": [
             {"billable": True,  "task": {"id": 20753151, "name": "Gen - Development/Configuration"}},
             {"billable": False, "task": {"id": 20878969, "name": "Gen - Development/Configuration (NB)"}}]}]}
    page7 = {"project_assignments": [
        {"project": {"id": 37122824, "code": "ACL-001", "name": "Admin"},
         "task_assignments": [
             {"billable": False, "task": {"id": 20759111, "name": "Meeting - Standup Meetings"}}]},
        {"project": {"id": 48084036, "code": "NLS-CR202", "name": "CMS Backlog Phase 2"},
         "task_assignments": []}]}  # duplicate project id, must be de-duped
    with open(os.path.join(mcp_dir, "harvest_assignments.json"), "w", encoding="utf-8") as f:
        json.dump(page1, f)
    with open(os.path.join(mcp_dir, "harvest_assignments_p7.json"), "w", encoding="utf-8") as f:
        json.dump(page7, f)


def test_finds_project_on_first_page_across_pages(tmp_path):
    _write_catalog(str(tmp_path))
    rows = list(hl.iter_assignments(str(tmp_path)))
    ids = [r["project"]["id"] for r in rows]
    assert ids.count(48084036) == 1          # de-duped across pages
    assert 37122824 in ids


def test_lookup_returns_billable_task(tmp_path):
    _write_catalog(str(tmp_path))
    matches = hl.lookup("NLS-CR202", str(tmp_path))
    assert len(matches) == 1
    m = matches[0]
    assert m["project_id"] == 48084036
    dev = [t for t in m["tasks"] if t["id"] == 20753151][0]
    assert dev["billable"] is True


def test_cli_exit_nonzero_on_no_match(tmp_path):
    _write_catalog(str(tmp_path))
    r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "harvest_lookup.py"),
                        "NOPE", "--mcp-dir", str(tmp_path)], capture_output=True, text=True)
    assert r.returncode != 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_harvest_lookup.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'harvest_lookup'`.

- [ ] **Step 3: Write the implementation**

`scripts/harvest_lookup.py`:

```python
"""Look up a Harvest project + its tasks by code or name fragment, searching
ALL paginated assignment catalog pages.

The skill's .mcp/ holds the user's /users/me/project_assignments split across
several files (harvest_assignments.json, _p2.json, ...). A naive "read the
latest file" lookup misses projects on other pages — this searches every page
and de-dupes projects that appear on more than one.

Usage:
  python scripts/harvest_lookup.py NLS-CR202
  python scripts/harvest_lookup.py "Short Courses"
  python scripts/harvest_lookup.py CON --task Development
  python scripts/harvest_lookup.py NLS-CR202 --mcp-dir /path/to/.mcp --json
"""
import argparse
import glob
import json
import os
import sys

for _s in (sys.stdout, sys.stderr):   # pytest's captured stdout lacks reconfigure
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass


def find_catalog_dir(explicit):
    if explicit:
        return explicit
    for cand in [os.path.join(os.getcwd(), ".mcp"),
                 os.path.join(os.path.expanduser("~"), "Claude", "Work", ".mcp")]:
        if os.path.isdir(cand):
            return cand
    return os.path.join(os.getcwd(), ".mcp")


def iter_assignments(mcp_dir):
    """Yield each project_assignment dict across all catalog pages, de-duped by project id."""
    files = sorted(glob.glob(os.path.join(mcp_dir, "harvest_assignments*.json")))
    seen = set()
    for f in files:
        try:
            with open(f, encoding="utf-8") as fh:
                d = json.load(fh)
        except Exception:
            continue
        rows = d if isinstance(d, list) else d.get("project_assignments", d.get("assignments", []))
        for pa in rows:
            pid = (pa.get("project") or {}).get("id")
            if pid in seen:
                continue
            seen.add(pid)
            yield pa


def lookup(query, mcp_dir, task_filter=None):
    q = query.lower()
    matches = []
    for pa in iter_assignments(mcp_dir):
        p = pa.get("project") or {}
        code = p.get("code") or ""
        name = p.get("name") or ""
        if not (code.lower() == q or q in code.lower() or q in name.lower()):
            continue
        tasks = []
        for ta in pa.get("task_assignments", []):
            t = ta.get("task") or {}
            tname = t.get("name") or ""
            if task_filter and task_filter.lower() not in tname.lower():
                continue
            tasks.append({"id": t.get("id"), "name": tname, "billable": bool(ta.get("billable"))})
        matches.append({"code": code, "project_id": p.get("id"), "name": name, "tasks": tasks})
    matches.sort(key=lambda m: (m["code"].lower() != q, m["code"]))  # exact code first
    return matches


def main():
    ap = argparse.ArgumentParser(description="Look up a Harvest project + tasks by code/name.")
    ap.add_argument("query", help="project code (exact) or code/name fragment")
    ap.add_argument("--task", help="filter task rows by name substring (case-insensitive)")
    ap.add_argument("--mcp-dir", help="directory holding harvest_assignments*.json")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of text")
    args = ap.parse_args()

    mcp_dir = find_catalog_dir(args.mcp_dir)
    matches = lookup(args.query, mcp_dir, args.task)
    if not matches:
        print(f"No project matching '{args.query}' in {mcp_dir}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(matches, indent=2))
        return 0
    for m in matches:
        print(f"{m['code']}  {m['project_id']}  {m['name']}")
        for t in m["tasks"]:
            b = "billable" if t["billable"] else "NON-billable"
            print(f"    {t['id']}  {t['name']}  ({b})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_harvest_lookup.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Real-data smoke check**

Run: `cd "C:\Users\c.parsons\Claude\Work" && python "C:\Users\c.parsons\.claude\skills\daily-timesheet\scripts\harvest_lookup.py" NLS-CR202`
Expected: a line `NLS-CR202  48084036  CMS Backlog Requirements Implementation Phase 2` followed by `    20753151  Gen - Development/Configuration  (billable)`.

- [ ] **Step 6: Commit**

```bash
git add scripts/harvest_lookup.py tests/test_harvest_lookup.py
git commit -m "feat(daily-timesheet): add harvest_lookup.py paginated project/task lookup"
```

---

### Task 2: `activity_timeline.py` — categorized window timeline + zoom mode

**Goal:** A bundled script that renders the day's foreground-window activity as merged, AW-category-tagged spans plus a per-category day rollup, with a `--window` zoom mode that adds web-watcher detail — the permanent replacement for the throwaway binning script.

**Files:**
- Create: `scripts/activity_timeline.py`
- Create: `tests/test_activity_timeline.py`

**Acceptance Criteria:**
- [ ] `categorize(app, title, classes)` returns the labels of every class whose compiled regex matches `"{app} {title}"`; `[]` when none match.
- [ ] `build_window_spans(events, classes)` merges consecutive events sharing a category when the inter-event gap `< 60s`, tags each span (`uncategorized` when no class matches), and flags spans where any event matched multiple classes.
- [ ] Default run prints merged spans (time range, minutes, category, top window titles) and a per-category day-totals rollup including `uncategorized`.
- [ ] `--window HH:MM-HH:MM` restricts to that range AND lists firefox+chrome web events (time, title, url) for it.
- [ ] Stdlib only; `--utc-offset` and `--json` behave like `afk_blocks.py`; sub-5s events dropped.

**Verify:** `python -m pytest tests/test_activity_timeline.py -v` → all pass; and `cd <workspace> && python <skill>/scripts/activity_timeline.py 2026-06-19` → prints NZLS-dominated morning spans, a CV-heavy uncategorized afternoon, and a category rollup.

**Steps:**

- [ ] **Step 1: Write the failing test**

`tests/test_activity_timeline.py`:

```python
import os, re, sys
SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts")
sys.path.insert(0, SCRIPTS)
import activity_timeline as at

CLASSES = [
    ("NZLS", re.compile("NZLS", re.IGNORECASE)),
    ("Connexis", re.compile("Connexis", re.IGNORECASE)),
]


def _ev(ts, dur, app, title):
    return {"timestamp": ts, "duration": dur, "data": {"app": app, "title": title}}


def test_categorize_matches_and_misses():
    assert at.categorize("Code.exe", "Welcome - NZLS - Visual Studio Code", CLASSES) == ["NZLS"]
    assert at.categorize("msedge.exe", "Find Cheap Flights - Google Flights", CLASSES) == []


def test_build_spans_merges_same_category_and_breaks_on_change():
    evs = [
        _ev("2026-06-19T00:00:00+00:00", 120, "Code.exe", "Welcome - NZLS"),
        _ev("2026-06-19T00:02:00+00:00", 120, "msedge.exe", "CMS Board - NZLS"),  # same cat, gap 0
        _ev("2026-06-19T00:10:00+00:00", 120, "msedge.exe", "Overleaf CV"),       # uncategorized, gap 8min
    ]
    spans = at.build_window_spans(evs, CLASSES)
    assert len(spans) == 2
    assert spans[0]["category"] == "NZLS"
    assert spans[1]["category"] == "uncategorized"


def test_multi_match_flagged():
    evs = [_ev("2026-06-19T00:00:00+00:00", 60, "x", "NZLS and Connexis both")]
    spans = at.build_window_spans(evs, CLASSES)
    assert spans[0]["multi"] is True


def test_sub5s_dropped():
    evs = [_ev("2026-06-19T00:00:00+00:00", 3, "x", "NZLS blip")]
    assert at.build_window_spans(evs, CLASSES) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_activity_timeline.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'activity_timeline'`.

- [ ] **Step 3: Write the implementation**

`scripts/activity_timeline.py`:

```python
"""Window-activity timeline for the daily-timesheet skill, tagged with the
client categories ActivityWatch already knows.

afk_blocks.py gives the day *skeleton* (start/end/breaks). This gives the
*content*: a high-resolution, merged timeline of foreground-window activity,
each span tagged with the AW category (client) whose class-rule it matches.
Spans that match no class are "uncategorized"; spans matching several are
flagged — both are exactly the spans to confirm with --window or a screenshot.

AW category rules are read live from GET /api/0/settings -> "classes", so the
tags mirror what the AW web UI shows (regex on the window app + title). The
rules are *client*-level, not project/ticket-level: they get you to "NZLS",
never to "NLS-CR202 vs NLS2232S", and are a first-pass signal only — never
taken as 100% certain.

Two modes:
  * default              -> merged category spans for the whole day + per-category
                            day totals (the "bin rollup").
  * --window HH:MM-HH:MM -> zoom one section AND fold in the web watchers
                            (firefox + chrome) URLs/titles for it.

No third-party deps — stdlib urllib, like the sibling helpers.

Usage:
  python scripts/activity_timeline.py 2026-06-19
  python scripts/activity_timeline.py 2026-06-19 --window 12:30-14:00
  python scripts/activity_timeline.py 2026-06-19 --json
  python scripts/activity_timeline.py 2026-06-19 --utc-offset 13   # NZDT
"""
import argparse
import datetime as dt
import json
import re
import sys
import urllib.request

AW_BASE = "http://localhost:5600/api/0"
NOISE_FLOOR = 5    # drop sub-5s events (tab-switch noise), per SKILL.md
GAP_FOLD = 60      # inter-event gaps shorter than this don't break a span (seconds)

for _s in (sys.stdout, sys.stderr):   # pytest's captured stdout lacks reconfigure
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass


def _get(path):
    with urllib.request.urlopen(AW_BASE + path, timeout=15) as r:
        return json.load(r)


def discover_bucket(prefix):
    buckets = _get("/buckets/")
    cands = [b for b in buckets if b.startswith(prefix)]
    cands.sort(key=lambda b: ("_" not in b, b))  # prefer hostname-suffixed live buckets
    return cands[0] if cands else None


def fetch_events(bucket, start_utc, end_utc):
    if not bucket:
        return []
    q = f"/buckets/{bucket}/events?start={start_utc}&end={end_utc}&limit=10000"
    return _get(q)


def dedupe_heartbeats(events):
    best = {}
    for e in events:
        ts = e["timestamp"]
        if ts not in best or e["duration"] > best[ts]["duration"]:
            best[ts] = e
    return sorted(best.values(), key=lambda e: e["timestamp"])


def parse_ts(ts):
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def load_classes():
    """Return [(label, compiled_regex), ...] from AW settings 'classes'.
    Skips non-regex rules (e.g. parent categories with type 'none')."""
    try:
        settings = _get("/settings")
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


def build_window_spans(events, classes):
    """Merge chronological window events into spans sharing a category.
    Each span: start, end (datetime), category, multi (bool), titles {label: secs}."""
    evs = dedupe_heartbeats(events)
    spans = []
    cur = None
    for e in evs:
        if e["duration"] < NOISE_FLOOR:
            continue
        s = parse_ts(e["timestamp"])
        en = s + dt.timedelta(seconds=e["duration"])
        app = e["data"].get("app", "?")
        title = e["data"].get("title", "") or ""
        cats = categorize(app, title, classes)
        primary = cats[0] if cats else "uncategorized"
        key = f"{app} | {title}"
        if (cur is not None and cur["category"] == primary
                and (s - cur["end"]).total_seconds() < GAP_FOLD):
            cur["end"] = max(cur["end"], en)
            cur["titles"][key] = cur["titles"].get(key, 0) + e["duration"]
            cur["multi"] = cur["multi"] or len(cats) > 1
        else:
            if cur is not None:
                spans.append(cur)
            cur = {"start": s, "end": en, "category": primary,
                   "multi": len(cats) > 1, "titles": {key: e["duration"]}}
    if cur is not None:
        spans.append(cur)
    return spans


def category_rollup(events, classes):
    """Minutes per category across all (deduped, >=5s) events."""
    totals = {}
    for e in dedupe_heartbeats(events):
        if e["duration"] < NOISE_FLOOR:
            continue
        cats = categorize(e["data"].get("app", "?"), e["data"].get("title", "") or "", classes)
        label = cats[0] if cats else "uncategorized"
        totals[label] = totals.get(label, 0) + e["duration"]
    return {k: round(v / 60, 1) for k, v in sorted(totals.items(), key=lambda kv: -kv[1])}


def _utc_bounds(local_date, offset):
    local_start = dt.datetime.combine(local_date, dt.time(0, 0))
    start_utc = (local_start - offset).strftime("%Y-%m-%dT%H:%M:%SZ")
    end_utc = (local_start + dt.timedelta(days=1) - offset).strftime("%Y-%m-%dT%H:%M:%SZ")
    return start_utc, end_utc


def _parse_window(window, local_date, offset):
    a, b = window.split("-")
    ws = (dt.datetime.combine(local_date, dt.datetime.strptime(a.strip(), "%H:%M").time())
          - offset).replace(tzinfo=dt.timezone.utc)
    we = (dt.datetime.combine(local_date, dt.datetime.strptime(b.strip(), "%H:%M").time())
          - offset).replace(tzinfo=dt.timezone.utc)
    return ws, we


def main():
    ap = argparse.ArgumentParser(description="Categorized window-activity timeline for one day.")
    ap.add_argument("date", help="YYYY-MM-DD (local date)")
    ap.add_argument("--utc-offset", type=float, default=12.0,
                    help="Local zone offset from UTC in hours (default 12 = NZST; 13 for NZDT)")
    ap.add_argument("--window", help="Zoom HH:MM-HH:MM and include web-watcher detail")
    ap.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    args = ap.parse_args()

    offset = dt.timedelta(hours=args.utc_offset)
    try:
        local_date = dt.datetime.strptime(args.date, "%Y-%m-%d").date()
    except ValueError:
        print(f"ERR bad date '{args.date}', expected YYYY-MM-DD", file=sys.stderr)
        return 2

    start_utc, end_utc = _utc_bounds(local_date, offset)
    try:
        win_bucket = discover_bucket("aw-watcher-window_")
        win_events = fetch_events(win_bucket, start_utc, end_utc)
    except Exception as e:
        print(f"ERR ActivityWatch unreachable at {AW_BASE} ({e})", file=sys.stderr)
        return 1
    classes = load_classes()

    def to_local(d):
        return (d + offset).strftime("%H:%M:%S")

    spans = build_window_spans(win_events, classes)
    rollup = category_rollup(win_events, classes)

    # Zoom mode: restrict spans + pull web watchers for the window.
    web_rows = None
    if args.window:
        try:
            ws, we = _parse_window(args.window, local_date, offset)
        except Exception:
            print(f"ERR bad --window '{args.window}', expected HH:MM-HH:MM", file=sys.stderr)
            return 2
        spans = [s for s in spans if s["end"] > ws and s["start"] < we]
        web_rows = []
        for pref in ("aw-watcher-web-firefox_", "aw-watcher-web-chrome_"):
            try:
                b = discover_bucket(pref)
                for e in dedupe_heartbeats(fetch_events(b, start_utc, end_utc)):
                    if e["duration"] < NOISE_FLOOR:
                        continue
                    t = parse_ts(e["timestamp"])
                    if t < ws or t > we:
                        continue
                    web_rows.append({"time": to_local(t), "secs": int(e["duration"]),
                                     "title": (e["data"].get("title") or "")[:60],
                                     "url": (e["data"].get("url") or "")[:80]})
            except Exception:
                pass
        web_rows.sort(key=lambda r: r["time"])

    result = {
        "date": args.date,
        "window_bucket": win_bucket,
        "spans": [{"start": to_local(s["start"]), "end": to_local(s["end"]),
                   "min": round((s["end"] - s["start"]).total_seconds() / 60, 1),
                   "category": s["category"], "multi": s["multi"],
                   "top_titles": sorted(s["titles"].items(), key=lambda kv: -kv[1])[:3]}
                  for s in spans],
        "rollup_min_by_category": rollup,
        "web": web_rows,
    }

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    hdr = f"Window timeline for {args.date} (offset UTC+{args.utc_offset:g})"
    if args.window:
        hdr += f"  [zoom {args.window}]"
    print(hdr)
    print(f"  window bucket: {win_bucket}   classes loaded: {len(classes)}")
    for s in result["spans"]:
        flag = " !MULTI" if s["multi"] else ""
        top = s["top_titles"][0][0][:64] if s["top_titles"] else ""
        print(f"  {s['start']}-{s['end']}  {s['min']:>5}m  {s['category']:<14}{flag}  {top}")
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_activity_timeline.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Real-data smoke check**

Run: `cd "C:\Users\c.parsons\Claude\Work" && python "C:\Users\c.parsons\.claude\skills\daily-timesheet\scripts\activity_timeline.py" 2026-06-19`
Expected: morning spans tagged `NZLS`, an afternoon dominated by `uncategorized` (CV/Overleaf/flights), and a rollup showing NZLS minutes plus a large `uncategorized` bucket. Then run with `--window 12:30-14:00` and confirm Overleaf/ChatGPT web rows appear.

- [ ] **Step 6: Commit**

```bash
git add scripts/activity_timeline.py tests/test_activity_timeline.py
git commit -m "feat(daily-timesheet): add activity_timeline.py categorized window timeline + zoom"
```

---

### Task 3: Per-monitor screenshot capture

**Goal:** Capture one readable PNG per physical monitor (`HH-MM-SS_m1.png`, `_m2.png`, …) instead of one stitched ultra-wide image, and make the setup script install `mss`.

**Files:**
- Modify: `scripts/screenshot_capture.py` (replace `ImageGrab.grab(all_screens=True)` save with per-monitor capture)
- Modify: `scripts/setup_screenshot_pipeline.ps1:45-52` (add an `mss` install alongside Pillow)
- Create: `tests/test_screenshot_capture.py`

**Acceptance Criteria:**
- [ ] `order_monitors(monitors)` returns monitor dicts sorted left-to-right by `left`, excluding the `mss` virtual `monitors[0]` bounding box.
- [ ] A capture writes one PNG per monitor named `<timestamp>_m1.png`, `_m2.png`, … into the dated folder; each PNG is the native resolution of its monitor (not downscaled, not stitched).
- [ ] Single-monitor (laptop-only) capture produces exactly one file `<timestamp>_m1.png`.
- [ ] `setup_screenshot_pipeline.ps1` installs `mss` if missing, same pattern as the Pillow check.
- [ ] pythonw-safe logging to `capture.log` is preserved.

**Verify:** `python -m pytest tests/test_screenshot_capture.py -v` → pass; then run `python scripts/screenshot_capture.py` once on the multi-monitor setup and confirm 3 `_mN.png` files of distinct native sizes; on laptop-only confirm a single `_m1.png`.

**Steps:**

- [ ] **Step 1: Write the failing test for the pure helper**

`tests/test_screenshot_capture.py`:

```python
import os, sys
SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts")
sys.path.insert(0, SCRIPTS)
import screenshot_capture as sc


def test_order_monitors_left_to_right_excludes_virtual():
    # mss convention: monitors[0] is the all-screens bounding box; [1:] are real.
    monitors = [
        {"left": 0, "top": 0, "width": 6400, "height": 1440},   # [0] virtual, must drop
        {"left": 2560, "top": 0, "width": 1920, "height": 1080},
        {"left": 0, "top": 0, "width": 2560, "height": 1440},
        {"left": 4480, "top": 0, "width": 1920, "height": 1080},
    ]
    ordered = sc.order_monitors(monitors)
    assert [m["left"] for m in ordered] == [0, 2560, 4480]
    assert len(ordered) == 3


def test_order_monitors_single():
    monitors = [
        {"left": 0, "top": 0, "width": 1920, "height": 1200},
        {"left": 0, "top": 0, "width": 1920, "height": 1200},
    ]
    assert len(sc.order_monitors(monitors)) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_screenshot_capture.py -v`
Expected: FAIL — `AttributeError: module 'screenshot_capture' has no attribute 'order_monitors'`.

- [ ] **Step 3: Rewrite `screenshot_capture.py` for per-monitor capture**

Replace the file body with (keeps the pythonw-safe logging header and dated-folder behavior; swaps the grab):

```python
"""
screenshot_capture.py
---------------------
Takes one screenshot PER MONITOR and saves them into a dated folder. Designed
to be fired by a Windows Task Scheduler trigger every ~2.5 minutes across the
workday. Run it with pythonw.exe (not python.exe) so no console window flashes.

`setup_screenshot_pipeline.ps1` (next to this file) registers the scheduled
task and installs the mss + Pillow dependencies; you normally don't run this
by hand.

Folder structure it produces (one file per monitor, left-to-right):
  SCREENSHOTS_DIR\
    2026-06-19\
      08-30-01_m1.png
      08-30-01_m2.png
      08-30-01_m3.png
    capture.log          (append-only; errors land here since there's no console)

Per-monitor files stay at native resolution, so window titles and code remain
readable when opened — a single stitched ultra-wide PNG gets downsampled to
mush. Laptop-only days produce just _m1.png.

Dependencies: mss (monitor enumeration + grab) and Pillow (PNG save). The setup
script installs both if missing.
"""

import os
import sys
import datetime

# Under pythonw.exe there is no console: sys.stdout / sys.stderr are None and
# any print() would crash. Redirect them to a log file so prints are safe.
if sys.stdout is None or sys.stderr is None:
    _log_dir = os.path.join(os.path.expanduser("~"), "Pictures", "WorkScreenshots")
    os.makedirs(_log_dir, exist_ok=True)
    _log_fh = open(os.path.join(_log_dir, "capture.log"), "a", encoding="utf-8", buffering=1)
    sys.stdout = _log_fh
    sys.stderr = _log_fh

import mss
from PIL import Image

# -- Configuration ----------------------------------------------------------
SCREENSHOTS_DIR = os.path.join(os.path.expanduser("~"), "Pictures", "WorkScreenshots")
# ---------------------------------------------------------------------------


def order_monitors(monitors):
    """Given mss's sct.monitors list, drop the virtual all-screens box (index 0)
    and return the real monitors ordered left-to-right by their 'left' edge."""
    real = monitors[1:] if len(monitors) > 1 else monitors
    return sorted(real, key=lambda m: m["left"])


def take_screenshots():
    today = datetime.date.today().strftime("%Y-%m-%d")
    folder = os.path.join(SCREENSHOTS_DIR, today)
    os.makedirs(folder, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%H-%M-%S")

    saved = []
    with mss.mss() as sct:
        for n, mon in enumerate(order_monitors(sct.monitors), start=1):
            shot = sct.grab(mon)
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
            filepath = os.path.join(folder, f"{timestamp}_m{n}.png")
            img.save(filepath, optimize=True)
            saved.append(filepath)

    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Saved {len(saved)} monitor(s) -> {folder}")
    return saved


if __name__ == "__main__":
    try:
        take_screenshots()
        sys.exit(0)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_screenshot_capture.py -v`
Expected: PASS (2 tests). (Note: the test only exercises `order_monitors`; it does not import-fail because `mss`/`PIL` import at module top — ensure both are installed in the test env, see Step 6.)

- [ ] **Step 5: Add `mss` to the setup script**

In `scripts/setup_screenshot_pipeline.ps1`, after the Pillow block (line 52), insert:

```powershell
# --- Ensure mss is installed (per-monitor capture) ------------------------
Write-Host "Checking mss..."
& $pipExe -c "import mss" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing mss (user scope)..."
    & $pipExe -m pip install --user --quiet mss
    if ($LASTEXITCODE -ne 0) { throw "Failed to install mss." }
}
```

Also update the `.SYNOPSIS` line (line 4) to read `installs the Pillow + mss dependencies and`.

- [ ] **Step 6: Live multi-monitor + laptop verification**

Run: `python -m pip install --user mss Pillow` (ensure deps), then `python scripts/screenshot_capture.py`.
Expected on the 3-monitor setup: three files `HH-MM-SS_m1.png` / `_m2.png` / `_m3.png` in today's folder, with sizes ~2560×1440, ~1920×1080, ~1920×1080 (distinct, native). Open one and confirm window titles are legible. Then (if feasible) undock to laptop-only and confirm a single `_m1.png`.

- [ ] **Step 7: Commit**

```bash
git add scripts/screenshot_capture.py scripts/setup_screenshot_pipeline.ps1 tests/test_screenshot_capture.py
git commit -m "feat(daily-timesheet): capture one PNG per monitor for readable screenshots"
```

---

### Task 4: Wire the new tools into SKILL.md

**Goal:** Update SKILL.md so the workflow uses `activity_timeline.py`, `harvest_lookup.py`, and per-monitor screenshots, and so the file list + reading guidance match reality.

**Files:**
- Modify: `SKILL.md` (Step 2/3 inputs, Step 4 classification, Step 5 disambiguation, "Reading the screenshot folder", "Files in this skill", plus a maintenance note on AW classes)

**Acceptance Criteria:**
- [ ] Step 2/3 instruct running `python scripts/activity_timeline.py <date>` to get the categorized window timeline + rollup (replacing the manual-binning narrative).
- [ ] Step 4 states AW category is a first-pass *client* signal only — verify via context.md/screenshots, never taken as 100% certain; project/task still from ticket/work-item signals.
- [ ] Step 5 lists `activity_timeline.py --window …` (web watchers folded in) as the first disambiguation step, screenshots second.
- [ ] "Reading the screenshot folder (Windows)" documents the `_mN.png` per-monitor files and says to read the relevant monitor, not a stitched image.
- [ ] "Files in this skill" lists `activity_timeline.py` and `harvest_lookup.py` with one-line descriptions; project/task-ID lookup steps reference `harvest_lookup.py`.
- [ ] A maintenance note records that AW `classes` are now a live signal: fill the `New class`/`FILL ME` placeholder, add missing clients (Cone Marshall, Heart Foundation, …), and that the "CON2005 Short Courses under the EarnLearn Edge profile" caveat still needs manual handling because a client-level regex can't catch it.

**Verify:** `grep -n "activity_timeline.py\|harvest_lookup.py\|_m1.png\|_mN" SKILL.md` returns hits in the Workflow steps, the screenshot-reading section, and the file list; manual read confirms the six criteria above.

**Steps:**

- [ ] **Step 1: Edit the data-source + screenshot-reading sections**

In the "Data sources" → "Reading the screenshot folder (Windows)" section, change the file description to note per-monitor naming and update the example to list `_mN.png` files; add a sentence: "Each tick now writes one PNG per monitor (`HH-MM-SS_m1.png`, `_m2.png`, …), left-to-right. Read the monitor that shows the active app — not a stitched image. Older days may still hold single stitched PNGs."

- [ ] **Step 2: Edit Step 2 (Load inputs) and Step 3 (Block the day)**

Add to Step 2's parallel reads: "Run `python scripts/activity_timeline.py <date>` for the categorized window timeline + per-category day rollup." In Step 3, add after the `afk_blocks.py` paragraph: "`afk_blocks.py` gives the skeleton (start/end/breaks); `activity_timeline.py` gives the categorized window content you classify around. Run both."

- [ ] **Step 3: Edit Step 4 (Classify) and Step 5 (Disambiguate)**

In Step 4, add a new first bullet: "**AW category signal (first-pass client):** `activity_timeline.py` tags each span with the client category AW already knows (NZLS, Connexis, …). Treat it as a strong *client*-level hint, never 100% certain and never project/ticket-level — confirm the project/task from ticket/work-item signals + `.context.md`, and verify ambiguous/`uncategorized`/`!MULTI` spans." In Step 5, make the first disambiguation step: "Run `activity_timeline.py <date> --window HH:MM-HH:MM` — it adds the firefox+chrome web rows for that section. Reach for screenshots only if the web/window detail is still ambiguous."

- [ ] **Step 4: Edit the project/task-lookup references**

Where Step 4/Step 9 describe looking up `project_id`/`task_id` from `.mcp/harvest_assignments*.json`, add: "Use `python scripts/harvest_lookup.py <code-or-name>` — it searches all assignment pages and prints `project_id` + each task's id/name/billable. Don't hand-roll the glob (it's easy to read only one page and miss the project)."

- [ ] **Step 5: Update the "Files in this skill" list**

Add two entries:
```
- `scripts/activity_timeline.py` — categorized window-activity timeline (merged spans + per-category day rollup); `--window` zooms a section and folds in web-watcher detail. Run in Step 2/3 to get the content you classify around.
- `scripts/harvest_lookup.py` — look up a Harvest project + its tasks by code/name across ALL `.mcp/harvest_assignments*.json` pages. Use whenever you need project_id/task_id.
```

- [ ] **Step 6: Add the AW-classes maintenance note**

Under "Setup (first-run + ongoing)" (or a new "## ActivityWatch categories" subsection), add: "The skill reads your AW category rules live from `/api/0/settings`. They're client-level regex on window titles. Keep them useful: fill the placeholder `New class` (`FILL ME`) rule, add missing clients (Cone Marshall, Heart Foundation, etc.), and remember a client-level regex can't catch work-content overrides like 'CON2005 Short Courses under the EarnLearn Edge profile' — that still needs the manual `.context.md` rule."

- [ ] **Step 7: Verify and commit**

Run: `grep -n "activity_timeline.py\|harvest_lookup.py\|_m1.png" SKILL.md`
Expected: hits in Workflow Step 2/3, Step 4, Step 5, the screenshot-reading section, and the file list.

```bash
git add SKILL.md
git commit -m "docs(daily-timesheet): wire activity_timeline/harvest_lookup/per-monitor screenshots into SKILL.md"
```

---

## Backup to claude-skills repo (after all tasks)

After Task 4, back the skill up via the claude-skills-repo skill's manual mirror (never copies `.env`):

```powershell
$live="$HOME\.claude\skills\daily-timesheet"; $repo="C:\Users\c.parsons\claude-skills\skills\daily-timesheet"
robocopy $live $repo /MIR /XF .env /XD __pycache__ .git /NJH /NJS | Out-Null
cd C:\Users\c.parsons\claude-skills
git add skills/daily-timesheet
git diff --cached --name-only   # confirm NO .env present
git commit -m "Update daily-timesheet: activity_timeline, harvest_lookup, per-monitor screenshots"
git push
```
Then verify `.env` is absent on the remote: `gh api repos/Cordedmink2/claude-skills/contents/skills/daily-timesheet/.env` → 404.

## Notes for the implementer

- Run all commands from the skill root `C:\Users\c.parsons\.claude\skills\daily-timesheet` unless a step says otherwise; the real-data smoke checks `cd` to the workspace `C:\Users\c.parsons\Claude\Work` because that's where `.mcp/` and live AW data live.
- `pytest` and `mss` may need installing first: `python -m pip install --user pytest mss Pillow`.
- The skill folder is NOT a git repo on its own — "commit" steps are conceptual checkpoints; the real version control is the `claude-skills` repo backup at the end. If you prefer per-task commits, run them inside `C:\Users\c.parsons\claude-skills` after mirroring, or treat each task's commit as a logical boundary and do the single backup at the end.
