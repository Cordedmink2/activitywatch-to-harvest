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

- **Time format**: `HH:MM` 24-hour, in the user's local timezone (from `.context.md` `## Preferences`). The separator between start and end is the en-dash `–` (U+2013), not a hyphen.
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
