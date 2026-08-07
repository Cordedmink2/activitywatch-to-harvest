# ActivityWatch raw API reference

The bundled scripts (`afk_blocks.py`, `activity_timeline.py`) wrap this API and handle the pitfalls below — prefer them. Query AW raw only when a script can't answer the question (e.g. pulling web-watcher events outside a timeline zoom, or debugging a watcher).

## Endpoints

- Discover buckets: `GET http://localhost:5600/api/0/buckets/` returns `{bucket_id: {...}}`. Buckets are hostname-suffixed (e.g. `aw-watcher-window_<HOST>`). A machine rename or reimage leaves the old-host buckets in the listing, no longer updating — `aw_client.py`'s `pick_bucket()` prefers a suffixed match over an unsuffixed leftover, and among suffixed candidates breaks ties by `last_updated`, so a stale old-host bucket won't get silently selected once the new one starts reporting.
- Pull events: `GET http://localhost:5600/api/0/buckets/<bucket_id>/events?start=<ISO-UTC>&end=<ISO-UTC>&limit=10000`. Events have `timestamp` (UTC), `duration` (seconds), `data` (varies by watcher).

## Buckets (`<host>` = machine hostname, discover via buckets endpoint)

- `aw-watcher-window_<host>` — `data.app`, `data.title`. Primary classifier signal.
- `aw-watcher-afk_<host>` — `data.status` is `"afk"` or `"not-afk"`. Primary break-detection signal.
- `aw-watcher-web-firefox_<host>` — `data.url`, `data.title` for Firefox tabs. Full URLs expose ChatGPT project slugs, Azure DevOps paths, SharePoint URLs.
- `aw-watcher-web-chrome_<host>` — same shape for Edge/Chrome tabs.
- `aw-watcher-vscode_<host>` — exact files/projects open in VS Code (when watcher is enabled — may be stale).

## Time zones

AW stores everything in UTC. Compute the UTC range from the user's *local-midnight* boundaries. Example for `2026-05-13` in NZST (UTC+12): `[2026-05-12T12:00:00Z, 2026-05-13T12:00:00Z]`. Read the user's timezone from `## Preferences` in `.context.md`; default to `Pacific/Auckland` if absent. Watch for DST transitions in the offset (UTC+13 during NZ daylight saving).

## Manual blocking spec (AW unreachable — `compact.jsonl` fallback only)

When ActivityWatch is down and the day comes from `daily_exports/<date>/compact.jsonl`, the scripts can't run — apply their spec by hand:

- `active_ratio = (block_duration − sum_of_AFK_overlapping_block) / block_duration`, judged on the same 0.7 / 0.4 bands as Step 3.
- **Lunch** = the longest contiguous `afk` event between roughly 11:30 and 14:30, *if* ≥ the break threshold (default 1050s). Other breaks = any `afk` ≥ threshold within the workday.
- `work_end` = end of the last `not-afk` event; never the last window event.
- Note `compact.jsonl` is pre-filtered (sub-10s events already dropped) — don't re-apply the 5s noise floor and don't treat its event count as complete.

## Pitfalls when reading raw events

- Drop events with `duration < 5` to remove tab-switch noise.
- **AW emits "heartbeat" updates.** A single ongoing activity often shows up as multiple events with the *same* `timestamp` but progressively longer `duration` — AW extends the existing event as time passes. When binning or counting, dedupe by `(timestamp → longest duration)` rather than summing across the duplicates, or you'll double-count.
- **`data.app == "unknown"` (or empty `data.title`) usually means the screen is locked** — Windows replaces the foreground app with `LockApp.exe`, which AW logs as `unknown`. The AFK watcher will also read `afk` for the same window. Don't bill these spans; they're either short interruptions (fold-in rule) or real breaks.
- Events come back reverse-chronological (latest first); reverse to chronological before grouping.
- **Background-polling pages emit 0-duration event streams** (e.g. the Power Platform admin center refreshing itself). The bundled scripts filter most of this — ignore remaining short blips rather than reading them as activity.
