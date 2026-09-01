---
name: reconcile
description: Reconcile a month against the activity data — find the days that were worked but never billed, or billed short, and say what was happening on each. Produces a worklist to take into the daily skill; records no time itself. User-invoked.
compatibility: Runs the `daily` skill's bundled Python scripts from a sibling directory, so it needs Python 3.10+ on the PATH and a harness that can execute local commands. Reads a running ActivityWatch server (default http://localhost:5600) and needs Harvest credentials to list the month. Investigating the gap days in parallel needs a harness that can dispatch subagents; without one they are worked through in sequence.
disable-model-invocation: true
---

# reconcile

One question, asked of a month: **which days were worked but never billed, or billed short — and what was actually happening on them.**

The answer is a worklist, not a report. Every row names a date, what the evidence says was going on, and the next action. Nothing here records time: a day this run finds is billed by the `daily` skill, which drafts it properly against the rubric and asks before it writes.

The shape below is what makes it affordable. Two cheap reads find the month's gaps; only the gaps are investigated, and that is usually two to five days rather than all twenty-two. Read the whole file before starting — Step 2 is where the cost is decided.

## What this covers, and what it does not

- **It reads and proposes.** Blocks are drafted by the `daily` skill, entries are recorded by it, and both happen on one date at a time behind its confirmation gate. This run opens nothing to draft.
- **It does not decide whether a day should have been billed.** Leave, a public holiday, a day the user chose not to work — none of those are visible in the data, and guessing produces a worklist with rows nobody can action. Where the evidence runs out, the row says so and asks.
- **It is a sweep, not a rewrite.** A day already billed is out of scope even if it looks odd; verifying an existing day against the evidence is the `daily` skill's already-covered branch, and it belongs to a run scoped to that date.

## Finding the files this skill needs

Every command below runs a script that ships with the `daily` skill, in a directory beside this one. Resolve **this** skill's folder from where this `SKILL.md` was read, then look for a sibling named `daily` — or, in the shared export, `billables-daily`, because that directory is flat and every skill in it is prefixed. Check which of the two exists rather than guessing; a wrong prefix fails as "file not found", which reads like a broken install rather than a wrong path. Resolve it once and reuse it for the whole run.

`python` in those commands means the interpreter this machine actually uses. `Timesheets/.context.md` records one if a previous run resolved it; otherwise, on Windows prefer `py` — a bare `python` is often the Store app-execution stub, whose tell is a help message about installing from the Store and exit code 49.

The month listing needs the configured Harvest credentials and the day skeletons need `TIMESHEET_TIMEZONE`. A run that stops naming one of those keys is a configuration gap: route it to `/plugin configure billables`, or to the `.env` beside the sibling skill's `SKILL.md` on an exported install. Do not ask for a value here.

## Step 1 — Sweep the month in two cheap reads

Resolve the month first. "August", "last month", "this month" convert using today's date in the user's timezone. The range is the first of the month to the last, **and it stops at yesterday** — today is in progress, so its billed total is not short, it is unfinished, and sweeping it produces a worklist row for a day that is still being worked. Where today falls inside the month asked for, say so in one line at the end rather than putting it in the table.

**On the first of a month there is no range left.** "This month", asked on the 1st, ends the day before it starts; so does a month that has not begun. Say there is nothing in it to reconcile yet and offer the month before — do not hand the reversed range to the listing, which refuses it with an error that reads like a broken install.

Then two reads, in parallel, and nothing else:

1. **What is already billed**, one row per date:
   ```
   python "<daily>/scripts/harvest_list.py" <first> <last> --by-day
   ```
   Every date in the range gets a row, including the ones holding nothing: `<date>  <Day>  <total>h  <n> entries  <project codes>`. The dates holding nothing are the candidates; the codes on a thin day are what a short day was billed to.
2. **Which days the machine was used**, as a date index: list the *folder names* under the screenshot directory, resolved first from `TIMESHEET_SCREENSHOTS_DIR`, or `~/Pictures/WorkScreenshots` where that is unset. Substitute the resolved path — reading the literal one on a machine that configured another finds an empty folder, and an empty index makes a healthy month look like a month nobody worked. One listing of directory names, not their contents:
   ```powershell
   Get-ChildItem "<screenshots-dir>" -Directory | Select-Object -ExpandProperty Name
   ```
   `daily_exports/` carries the same index where it exists and is the fallback when the capture directory is absent.

**The index is a proxy, and a narrow one.** It answers "was this machine used" only for the hours the capture task runs — weekdays, roughly 08:30 to 20:00, on Windows. It is silent, not negative, about a weekend, an evening, a second machine, and every macOS and Linux install, where no capture pipeline ships at all. So a date the index does not list is a date with *no evidence either way*, never a date nobody worked.

**Where the index is silent for the whole month** — a non-Windows install, or every date after the capture task died — say so and ask the user **which dates they worked**. Ask it that way round, not "which were leave": the sort below promotes a date on evidence that it *was* worked, so a list of days off leaves every remaining date unexplained and nothing gets investigated. A date the user names is treated exactly as an indexed one from here on. Ask **before** Step 3 dispatches anything.

The authority on whether a given date holds activity is the activity source, one `afk_blocks.py` run per date. That is the right answer for a date the user disputes and the wrong one for a whole month, which is why neither read above touches it. Open no day here.

## Step 2 — Drop the days already billed

Every date in the range gets one of five verdicts, decided from the two reads alone. The first two are the subtraction — they are settled here and never reach a subagent.

| Billed total | The index | Verdict |
|---|---|---|
| at or above the floor | either | **Billed** — out of scope. Not investigated, not dispatched, not mentioned again except in the count |
| any | date named by the user as leave, a holiday or a day off | **Not worked** — out of scope, for the reason the user gave |
| none | lists the date, or the user says they worked it | **Gap** — investigate |
| under the floor | lists the date, or the user says they worked it | **Short** — investigate |
| none or under the floor | silent, and unnamed either way | **Unexplained** — one line in the worklist, not a dispatch |

**Unexplained is a real verdict, not a rounding error.** It is where a weekend, an evening, a second machine and every non-Windows install land, and there is nothing to investigate on it because there is no evidence that anything happened. Never fold it into "not worked": the index being silent is not the machine being idle. List those dates in one line and let the user answer — a "yes, I worked that Saturday" turns one of them into a gap, and *then* it is worth a subagent. The counts have to add up to the days in the range, which is what stops a date falling between the rows.

The **short-day floor** is a preference, not a fact about anyone's day: `## Preferences` in `Timesheets/.context.md` sets it, defaulting to `6.0 hrs`. It decides only *who gets investigated*. Whether a day was genuinely billed short is a comparison of its billed hours against its own active minutes, and that happens in Step 3 with the day skeleton in hand — a four-hour day that was a four-hour day is not short, and the floor cannot know that.

**A run of capture-less days is one finding, not many.** When the index stops on a date and never resumes, that is a capture task that stopped firing — the failure that arrives silently and looks exactly like a month of not working. Every date after it is *Unexplained* by the rule above, so the sweep already declines to call them idle; what it owes the user is the maintenance finding, once. `references/setup.md` in the `daily` skill owns the diagnosis; the health check is `Get-ScheduledTaskInfo -TaskName WorkScreenshots`, where `LastTaskResult` of `0` is a task that last ran cleanly and `0x80070002` is the interpreter having moved.

State the split in one line before going further — `30 dates: 16 billed, 3 gaps, 2 short, 1 not worked, 8 unexplained` — so the user can see the shape of the month and stop an investigation that is about to be pointless. **If more than about eight days are candidates, ask before dispatching.** A month nobody billed is usually explained by a fact this run does not have — leave, a contract that started mid-month, a second timesheet — and eight investigations are an expensive way to be told that.

## Step 3 — Investigate each candidate day, one subagent per day

Each day is independent: nothing one day learns applies to another, and dispatching them together means one messy day neither slows the others down nor contaminates them with its evidence. The work per day is mechanical — run two scripts, read the output, report what is in it — so use the cheapest model that can do it (`model: "haiku"`).

One subagent per day. Never one per block: splitting a day into blocks is drafting, and drafting is the `daily` skill's with the rubric in hand.

A subagent has no conversation context, so its brief carries everything it needs:

- the date, the resolved scripts folder, and the interpreter to run them with;
- what Step 1 already found for that date — the billed total and the project codes, or that there is nothing;
- the path to `Timesheets/.context.md`, to be **read whole**, for that user's clients, signals and exclusions;
- the two commands, and no others, **with the scripts folder already substituted in** — a brief that hands on the bare `python scripts/…` spelling hands on a path that resolves against the workspace, where those scripts are not, and every day comes back as a missing file:
  - `python "<daily>/scripts/afk_blocks.py" <date>` — the day skeleton: work start, work end, breaks, active spans, active minutes;
  - `python "<daily>/scripts/activity_timeline.py" <date>` — the categorized window timeline. Compact output is the default and is enough; `--window HH:MM-HH:MM` zooms one ambiguous stretch. Never `--full`;
- the rules it does not get to break:
  - **active or idle is settled by the AFK watcher.** Never re-inferred from screenshots, and never from how long a window sat in focus;
  - **screenshots are read by timestamp, for a stretch the timeline could not name** — a few captures, never the folder;
  - **report raw signals, never a billing verdict.** Which client, which project and whether it bills are decided against the rubric, later, on the day's own run.

Report back in a fixed shape, so the worklist assembles without re-reading anything and a day that resolved to nothing is visibly a day that resolved to nothing:

```
<date> — work HH:MM–HH:MM, active N min, billed X.XXh
Evidence: <client and work-item signals, with the timestamps they came from>
Unaccounted: <stretches of active time the billed total does not cover>
Unclear: <what could not be resolved, and what would resolve it>
```

## Step 4 — The worklist

Oldest date first, the order the `daily` skill takes them in:

```markdown
| Date | Active | Billed | What was happening | Next |
|---|---|---|---|---|
| 2026-08-11 Tue | 6.7h | — | ACM2231S and ACM2245S all morning, one meeting 10:00–10:30 | `/billables:daily 2026-08-11` |
| 2026-08-19 Wed | 7.9h | 1.5h | NWC-001 billed for the morning; the afternoon is on an ACME environment | `/billables:daily 2026-08-19` |
```

Under it, in one line each and in this order: the **Unexplained** dates, named, as a question — "the index says nothing about these five; were any of them worked?"; a day whose investigation came back `Unclear`, with what would resolve it; any maintenance finding from Step 2; and today, if the month asked for is the current one, as a day still in progress rather than a gap.

Close by saying plainly that nothing was recorded and nothing was changed, and that each row is billed by invoking `/billables:daily <date>` for one date at a time.

**A day the user explains — leave, a holiday, a client that bills elsewhere — is worth keeping.** Propose it for `Timesheets/.context.md` as one line under the exclusions, showing the exact diff, so next month's sweep does not ask the same question again. That file is the user's, so propose; never write it silently.

## Non-negotiables

- **Nothing here records time.** This run reads a month and proposes a worklist. Recording a day is the `daily` skill's, on that date's own run, and it asks first.
- **Already-billed days are dropped before anything is dispatched.** That subtraction is the whole cost argument; running it afterwards produces the same worklist for ten times the money.
- **Don't draft blocks.** Naming what was happening on a day is evidence. Splitting it, attributing it and pricing it is drafting, and a draft made here is a draft made without the rubric that governs it.
- **Don't invent a working day, and don't invent an empty one.** A date the index is silent about is a date with no evidence — *Unexplained*, and asked about. Reporting it as idleness is the same fabrication as reporting it as work; the index only ever covers weekday office hours on Windows.
- **Every number in the worklist came from a script.** Hours, active minutes and coverage are arithmetic — `afk_blocks.py` and the by-day listing own them, and a total summed by eye off a month of rows is wrong quietly.

## Files in this skill

- `SKILL.md` — this file. The reporting, correcting and month-close material arrives later, as references beside it.
