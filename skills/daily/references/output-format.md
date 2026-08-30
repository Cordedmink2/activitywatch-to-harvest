# Timesheet output format

The `Timesheets/<date>_timesheet.md` is an *optional* internal-audit artefact. Generate it only when the user asks for it. Match the structure below.

```markdown
# Timesheet — {{YYYY-MM-DD}}

**Total billable hours:** {{X.X}} hrs
**Total break time:** ~{{N}} mins (plus short interstitial breaks)
**Generated:** {{HH:MM}} {{LOCAL_TZ_ABBREV}}

## Time Blocks

| Time | Duration | Client | Description |
|------|----------|--------|-------------|
| {{HH:MM–HH:MM}} | {{X.XX hrs}} | {{Client}} | {{Description}} |
| {{HH:MM–HH:MM}} | *Break* | — | {{AFK reason or "AFK (~N min)"}} |
…

## Daily Total by Client

| Client | Hours |
|--------|-------|
| {{Client1}} | {{X.X}} |
| {{Client2}} | {{X.X}} |
| **Total** | **{{X.X}}** |

## Notes
- {{Judgment call or split worth user reviewing}}
- {{Any block where user's input changed the auto-classification}}
- {{Any time excluded as personal — keep brief}}

---
*Auto-generated from ActivityWatch + screenshots. Please review before submitting.*
```

## Conventions

- **Time format**: `HH:MM` 24-hour, in the user's local timezone (the configured `TIMESHEET_TIMEZONE` — which is what the scripts already render in, so their output needs no further conversion). The separator between start and end is the en-dash `–` (U+2013), not a hyphen.
- **A `*` on a time — the hour the clocks go back.** One hour of one day a year, the local clock repeats, and the scripts suffix the second pass: `02:30` is the first, `02:30*` the one an hour later. Three things follow, in the order you will hit them.
  - **Keep it in the markdown row.** `02:30*–04:15` is a different block from `01:30–02:30`, and without the marker two rows can read identically for time the user actually spent twice. Add a Notes bullet saying the clocks changed that day.
  - **Strip it before `harvest_post.py`.** Harvest takes a plain `HH:MM` and has no notion of the repeated hour; a `*` in the argument is a bad time, not a marked one.
  - **Never let one entry span the change.** Harvest subtracts the two clock times, so a stretch worked straight through — `01:30` to `04:15` in `Pacific/Auckland` on 2026-04-05 — posts as 2.75 hrs against the 3.75 hrs that really passed. Split it **at the transition**, which is the instant the scripts print as `02:00*`, and post two entries.

    The two notations differ at exactly that instant, which is the whole trap, so take the split in two steps:

    | | pre-change piece | post-change piece |
    | --- | --- | --- |
    | What the scripts print | `01:30 – 02:00*` | `02:00* – 04:15` |
    | What you post to Harvest | `01:30` – `03:00` | `02:00` – `04:15` |
    | Hours Harvest then bills | 1.5 | 2.25 |

    The transition instant has two clock readings — `03:00` as you reach it and `02:00` once the clocks have gone back — so the pre-change piece *ends* at `03:00` and the post-change piece *starts* at `02:00`. The two entries look like they overlap and do not; they abut. 1.5 + 2.25 = 3.75, the time really worked. Say in the Notes that the clocks changed, because the overlap is the first thing a reviewer will query.

    Do not reach for `03:00` in a script argument to mean that instant: to the scripts `03:00` is 15:00Z, an hour after the change, and only `02:00*` names it.

  Everywhere else the marker is absent, including every `--utc-offset` run, so there is nothing to do about it on the other 364 days. Splitting only arises for work that actually runs through the change; a day whose blocks sit either side of it, like a break across the hour, needs none of this.
- **Duration**: decimal hours rounded to 0.25 (`0.25`, `0.5`, `0.75`, `1.0`, …). Append ` hrs` literally.
- **Break rows**: *only* for breaks ≥17.5 min (or the user's overridden threshold). Render `*Break*` in italic, `—` em-dash in the Client column. Shorter AFK gaps fold silently into the surrounding work block.
- **Client column**: short canonical name as defined in `.context.md`, not the long Harvest client name.
- **Description (markdown column)**: 1 sentence, concrete, internal-audit style. The markdown file stays local — so it can mention tools, tickets, file names, participants if useful for review. Match the user's own tone (read existing files in `Timesheets/` or their Harvest history for examples).
- **Harvest `notes` field is different.** Those get sent to clients with invoices — follow `classification-rules.md` "Writing the Harvest note"; the user's own examples are in `.context.md` "How I bill".
- **Support tickets**: prefix description with `[Support] ` for tickets matching the support pattern (e.g. trailing `S` if defined in `.context.md`).
- **Notes section**: 3-6 bullets typically. Cover splits, judgment calls, exclusions. Skip trivial observations.

## Anti-patterns

Avoid (these feel "AI-generated"):
- "I observed that…" / "Based on the activity data…" / any preamble
- Em-dashes used for sentence-level pauses (use them only in time ranges or table cells)
- Marketing-style adjectives ("comprehensive", "robust", "leveraging")
- Bullet lists in the Description column — keep it one inline sentence
- Padding the Notes section with obvious facts ("user used Edge today")
