# ActivityWatch raw API reference

The bundled scripts (`afk_blocks.py`, `activity_timeline.py`) wrap this API and handle the pitfalls below — prefer them. Query AW raw only when a script can't answer the question (e.g. pulling web-watcher events outside a timeline zoom, or debugging a watcher).

## Endpoints

`<activity-url>` throughout is the configured `TIMESHEET_ACTIVITY_URL`, or `http://localhost:5600` when it is unset — which is the usual case. Use the configured one rather than the literal: on a machine reading a remote ActivityWatch, a raw query to localhost reports the instrument dead while the bundled scripts work fine.

- Discover buckets: `GET <activity-url>/api/0/buckets/` returns `{bucket_id: {...}}`. Buckets are hostname-suffixed (e.g. `aw-watcher-window_<HOST>`). A machine rename or reimage leaves the old-host buckets in the listing, no longer updating — `aw_client.py`'s `pick_bucket()` prefers a suffixed match over an unsuffixed leftover, and among suffixed candidates breaks ties by `last_updated`, so a stale old-host bucket won't get silently selected once the new one starts reporting.
- Pull events: `GET <activity-url>/api/0/buckets/<bucket_id>/events?start=<ISO-UTC>&end=<ISO-UTC>&limit=10000`. Events have `timestamp` (UTC), `duration` (seconds), `data` (varies by watcher).

## Buckets (`<host>` = machine hostname, discover via buckets endpoint)

- `aw-watcher-window_<host>` — `data.app`, `data.title`. Primary classifier signal.
- `aw-watcher-afk_<host>` — `data.status` is `"afk"` or `"not-afk"`. Primary break-detection signal.
- `aw-watcher-web-firefox_<host>` — `data.url`, `data.title` for Firefox tabs. Full URLs expose ChatGPT project slugs, Azure DevOps paths, SharePoint URLs.
- `aw-watcher-web-chrome_<host>` — same shape for Edge/Chrome tabs.
- `aw-watcher-vscode_<host>` — exact files/projects open in VS Code (when watcher is enabled — may be stale).

## Time zones

AW stores everything in UTC. Compute the UTC range from the user's *local-midnight* boundaries. Example for `2026-05-13` at UTC+12: `[2026-05-12T12:00:00Z, 2026-05-13T12:00:00Z]`. The zone is the configured `TIMESHEET_TIMEZONE` (`/plugin configure billables`), which `aw_client.resolve_zone` loads as a real zone, so a daylight-saving change is handled without anyone remembering it. **Do not substitute a zone of your own if it is unset** — the scripts refuse the run instead, deliberately: a guessed offset moves the day boundary by hours and nothing fails visibly.

Each end of the day is resolved separately, so the day the clocks change is *not* twenty-four hours long: `2026-04-05` in `Pacific/Auckland` runs `[2026-04-04T11:00:00Z, 2026-04-05T12:00:00Z]`, twenty-five hours, and the spring one is twenty-three. Five consequences worth expecting rather than querying:

- An elapsed span crossing the change reads an hour longer than its two clock times suggest — 01:45–09:15 is reported as 510 minutes, and that is the time that really passed.
- The hour a fall-back repeats is ambiguous on the clock, so **the scripts suffix the second pass over it with `*`**: `02:30:00` is the first 02:30 and `02:30:00*` is the one an hour later. It appears nowhere else — one hour of one day a year — and never on a `--utc-offset` run, whose zone has no repeated hour. Read it as part of the time and hand it back as part of the time: `--window 02:30*-04:15` and `--cover 01:30-02:30,02:30*-04:15` name the instants the spans came from. Unmarked still means the first pass, so every time written before this still means what it did.
- A break across that hour can show the same clock at both ends: `02:30:00 - 02:30:00*  (60.0 min)` is a real hour, not a rendering fault. Trust the minutes.
- A window written across the whole hour is two hours long in real time, so `--window 02:00-03:00` on `2026-04-05` reports `window_min` 120.0 and measures `active_ratio` against two hours. That is the honest denominator; don't read the low ratio as idleness. To measure one pass alone, mark it: `--window 02:00*-03:00`.
- The marker is only accepted where the clock really does read twice. `09:00*`, or `03:00*` on that same morning, is refused by name rather than quietly treated as unmarked — `03:00` is reached once, an hour *after* the change, so it does not name the transition. The instant the clocks go back is `02:00*`, and nothing else names it.
- The hour a spring-forward skips does not exist, so a `--window` inside it is refused by name rather than reported empty.

## Manual blocking spec (AW unreachable — `compact.jsonl` fallback only)

When ActivityWatch is down and the day comes from `daily_exports/<date>/compact.jsonl`, the scripts can't run — apply their spec by hand:

- `active_ratio = (block_duration − sum_of_AFK_overlapping_block) / block_duration`, judged on the same 0.7 / 0.4 bands as Step 3.
- **Lunch** = the longest contiguous `afk` event between roughly 11:30 and 14:30, *if* ≥ the break threshold (default 1050s). Other breaks = any `afk` ≥ threshold within the workday.
- `work_end` = end of the last `not-afk` event; never the last window event.
- Note `compact.jsonl` is pre-filtered (sub-10s events already dropped) — don't re-apply the 5s noise floor and don't treat its event count as complete.

## Pitfalls when reading raw events

- Drop events with `duration < 5` to remove tab-switch noise.
- **AW emits "heartbeat" updates.** A single ongoing activity often shows up as multiple events with the *same* `timestamp` but progressively longer `duration` — AW extends the existing event as time passes. When binning or counting, dedupe by `(timestamp → longest duration)` rather than summing across the duplicates, or you'll double-count.
- **`data.app == "unknown"` (or empty `data.title`) usually means the screen is locked** — Windows replaces the foreground app with `LockApp.exe`, which AW logs as `unknown`. The AFK watcher will also read `afk` for the same window. Don't bill these spans; they're either short interruptions (fold-in rule) or real breaks. A lock can also fragment the AFK record into chunks that each fall under the break threshold, so `afk_blocks.py` reports `breaks: (none)` for a day that plainly had them. Those stretches surface instead as sub-0.4 `active_ratio` windows with a matching gap in the screenshot captures — exclude them under the `<0.4` band rather than inventing a break the script never reported.
- Events come back reverse-chronological (latest first); reverse to chronological before grouping.
- **Background-polling pages emit 0-duration event streams** (e.g. the Power Platform admin center refreshing itself). The bundled scripts filter most of this — ignore remaining short blips rather than reading them as activity.
