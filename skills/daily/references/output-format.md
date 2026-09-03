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
- **A `*` on a time — the hour the clocks go back.** One hour of one day a year, the local clock repeats, and the scripts suffix the second pass: `02:30` is the first, `02:30*` the one an hour later. Four things follow, in the order you will hit them.
  - **Keep it in the markdown row.** `02:30*–04:15` is a different block from `01:30–02:30`, and without the marker two rows can read identically for time the user actually spent twice. Add a Notes bullet saying the clocks changed that day.
  - **Strip it before `harvest_post.py`.** Harvest takes a plain `HH:MM` and has no notion of the repeated hour; a `*` in the argument is a bad time, not a marked one.
  - **Never let one entry span the change.** Harvest subtracts the two clock times, so a stretch worked straight through — `01:30` to `04:15` in `Pacific/Auckland` on 2026-04-05 — would post as 2.75 hrs against the 3.75 hrs that really passed. `harvest_post.py` refuses that entry and names the two to post instead, with the arithmetic; do what it says and add a Notes bullet saying the clocks changed. Do not "fix" the overlap it warns you about — closing it is what loses the hour. `harvest_patch.py` refuses it too, on what the patch would *result* in, so a correction cannot arrive at that entry either — not by moving a time, and not by moving the date under fixed times. Two things it still lets through: `--hours`, which a duration-mode account needs and which on a start/end-time account does not do what it looks like (the script's module docstring has that trap), and an entry whose stored times it cannot read. Correct such an entry the same way you would post one — patch it to the first of the two ranges and post the second.
  - **A block that touches the repeated hour without straddling it is still yours to split.** The refusal covers only an entry whose two times are *strictly outside* the repeated hour, one either side. Anything else it has to let through, and there are two shapes:
    - **Ending exactly at `03:00`, or starting exactly at `02:00`.** Those are the two entries the refusal itself recommends, so it cannot refuse them — but they are also what you would type for a block that ran to 03:00 *after* the change (`01:30–03:00` is 2.5 hrs really worked and bills 1.5) or from 02:00 *before* it (`02:00–04:15` is 3.25 and bills 2.25). Same two arguments, two different mornings. If yours is the second kind, split it.
    - **Starting or ending inside the hour.** `02:15–04:15` — unmarked, so the first pass — bills 2.0 against the 3.0 really worked; `02:15*–04:15` strips to the same two arguments and 2.0 is right for it. `01:30–02:30*` is the mirror image: an hour billed for the two really worked.

    In every one of these the script sees one entry and cannot tell the two readings apart, so the split is on you. Split at the transition — the instant the scripts print as `02:00*` — and post the piece before it *ending* at `03:00` and the piece after it *starting* at `02:00`, which is the same pair of readings the refusal explains. Check the two pieces sum to the elapsed time before posting either.

    Do not reach for `03:00` in a script argument to mean that instant: to the scripts `03:00` is 15:00Z, an hour after the change, and only `02:00*` names it.

  Everywhere else the marker is absent, including every `--utc-offset` run, so there is nothing to do about it on the other 364 days. Splitting only arises for work that actually runs through the change; a day whose blocks sit either side of it, like a break across the hour, needs none of this.
- **Duration**: decimal hours rounded to 0.25 (`0.25`, `0.5`, `0.75`, `1.0`, …). Append ` hrs` literally.
- **Break rows**: *only* for breaks ≥17.5 min (or the user's overridden threshold). Render `*Break*` in italic, `—` em-dash in the Client column. Shorter AFK gaps fold silently into the surrounding work block.
- **Client column**: short canonical name as defined in `.context.md`, not the long client name the provider carries.
- **Description (markdown column)**: 1 sentence, concrete, internal-audit style. The markdown file stays local — so it can mention tools, work items, file names, participants if useful for review. Match the user's own tone (read existing files in `Timesheets/` or their posted entries for examples).
- **An entry's `notes` field is different.** Those get sent to clients with invoices — follow `classification-rules.md` "Writing the entry note"; the user's own examples are in `.context.md` "How I bill".
- **Support work**: prefix description with `[Support] ` for work items matching the support pattern (e.g. trailing `S` if defined in `.context.md`).
- **Notes section**: 3-6 bullets typically. Cover splits, judgment calls, exclusions. Skip trivial observations.

## Anti-patterns

Avoid (these feel "AI-generated"):
- "I observed that…" / "Based on the activity data…" / any preamble
- Em-dashes used for sentence-level pauses (use them only in time ranges or table cells)
- Marketing-style adjectives ("comprehensive", "robust", "leveraging")
- Bullet lists in the Description column — keep it one inline sentence
- Padding the Notes section with obvious facts ("user used Edge today")
