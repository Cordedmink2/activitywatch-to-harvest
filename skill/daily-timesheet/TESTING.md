# Testing & Improvement Record

Not part of the operating instructions. `SKILL.md` says what to do; this file holds
why it says it — test records, settled decisions with their evidence, and the options
that were considered and rejected. Read this before changing `SKILL.md`; skip it if
you are just running a timesheet.

Method: `changing-agent-instructions`. The rule that governs this file is **never
encode a diagnosis you have not watched happen**.

`references/self-development.md` is the process side — where maintenance content goes,
which gates a doc edit trips, the rules with more than one copy, and how a change gets
released. Read it alongside this file when changing the skill.

## What the instruments measure

`tests/` measures the *scripts*. It stays green when the instructions break, so it is
not the instrument for a `SKILL.md` change — it only guards against a doc edit that
invalidates a script path or command shape (`test_references.py`). How to run it and how
to add to it is in `tests/README.md`; script-level findings are recorded under "Script
defects" below.

For guidance changes the instrument is: same scenario, fresh agent, no filesystem
access, before vs after, 3+ reps read by hand. Variance across reps is the signal — three
different confident answers means the wording binds nothing.

**One measured baseline now exists** — the Step 3 lock-routing test of 2026-08-12 below,
which is a real two-arm before/after. Everything above it in this file predates that and
was written from live observation of a single real run, not from a measured control.

## Evidence rungs

Used below, strongest first:

1. **Observed failure** — the run failed, and the failure was the doc's.
2. **Observed hazard** — the underlying fact was measured, but no agent was watched
   getting it wrong.
3. **Reasoned** — neither. Should not reach `SKILL.md` without a test.

## Settled decisions

### Interpreter is resolved, not literal — `SKILL.md` "Running the scripts"
**Rung 1.** 2026-08-11. Every documented command read `python scripts/…`; on this
machine `python` is the Windows Store app-execution stub, which prints a help message
about installing from the Store and exits **49**. First script call of the run failed.
The exit-49-plus-help-text signature reads like a broken script, so the risk is
debugging the wrong thing.

Fix names the failure signature and points at `.context.md` for the machine's answer.

**Rejected: globally replacing `python` with `py`.** That is the same defect aimed
somewhere else — `py` is Windows-only and would break the skill for any other user.
Machine-specific facts belong in `.context.md` → Machine, which is where this one went.

### Capture-health check at index time — `SKILL.md` Step 3
**Rung 1.** 2026-08-11, billing 2026-08-10. The screenshot task had been dead since
13:32 (scheduled task pointed at `C:\Python314\pythonw.exe`; Python had been reinstalled
to `AppData` at 13:33, so every trigger failed `0x80070002` silently). The index was
listed at Step 3 and the gap was *not* noticed. It surfaced only at Step 5, when the
13:48–17:19 block turned ambiguous and the documented fallback — "then screenshots" —
turned out to be unavailable for exactly that span. The block shipped 🔸 to the user.

The disambiguating fact is that a short index looks identical whether the user stopped
working or the capture died; `work_end` separates the two and is already in hand at
Step 3. Cost of missing it is a block that could have been resolved becoming a question.

Deliberately *not* a "go fix the scheduler" instruction — that is maintenance, and
mixing it into a timesheet run is how a classification task turns into a yak shave.

### Skeleton freshness in the pre-post checklist — `SKILL.md` Step 8
**Rung 2 — weakest of the three, treat as provisional.** 2026-08-11. The session began
2026-08-10 19:37 and resumed the next morning. `work_end` moved 19:46 → 22:36, a new
22:34–22:36 active span appeared, and total active minutes moved 432.2 → 434.6, changing
the coverage denominator.

The hazard is measured. The *skip* is not: the skeleton was re-read spontaneously,
because an overnight resumption is an unmistakable cue. The untested case is the subtle
one — a long same-day session where the day is still open and nothing signals staleness.

**Test before keeping.** If a fresh agent re-reads the skeleton unprompted in the
same-day case, delete this line rather than leave a rule earning nothing.

### `--cover` takes posted entries, not billable ones — `SKILL.md` Step 8
**Rung 1, minor.** The guard said "proposed billed entries", disambiguated only by a
parenthetical. On this run `--cover` was first passed a stretch that was being
*excluded* (personal/tooling time), which is precisely the input that makes the guard
report clean while under-billing goes unnoticed — the failure it exists to catch. Re-run
was needed. Reworded to "every entry Step 9 will post, non-billable ones included", with
the explicit prohibition on feeding excluded stretches to `--cover`.

The rule has **two copies** — Step 6 guard 3 (which owns the explanation and the example
command) and the Step 8 checklist line. Fixing only the checklist copy left them saying
different things — "billed entries" vs "every entry posted" — which is the scope-drift
shape: each reads fine alone, the contradiction only exists across them, and the *unfixed*
copy was the one read first. Both are now aligned; Step 6 owns the reasoning and Step 8
restates the check. A diff self-grep caught exclusivity claims but not this, because it
searched for a phrase rather than for the rule's other copy. **Search for the rule, not the
wording.**

### No Step 3 pointer to the lock-screen quirk — measured and rejected
**Measured, 2026-08-12. The first fresh-agent two-arm test in this file.**

The worry: `SKILL.md` routes `references/activitywatch.md` only as a *raw-API* reference —
the data-sources table ("query raw only per…") and the AW-unreachable fallback at Step 2.
The lock-fragmentation fact matters at **Step 3, with AW up and the bundled scripts
working**, which is the one case neither route covers. Step 3 also carries a hard "do not
invent a break" rule, so an agent seeing `breaks: (none)` on a day that plainly had breaks
looked exposed.

**Method.** Fictional consultant and clients, no tools, reference files named but declared
unavailable. Fixture: `breaks: (none)`, elapsed 492.5 min vs active 363.0, three `unknown`
window stretches, screenshot gaps coextensive with all three. Arm A = Step 3 as shipped.
Arm B = Step 3 plus one bullet ("an empty `breaks` list on a long day is a signal, not a
fact… most often screen lock… see `references/activitywatch.md`"). 3 reps each, all six
read by hand, zero tool uses in any rep.

**Result: 6/6 identical.** Same four blocks; all three stretches excluded under the `<0.4`
band; no rep invented a break; every rep checked the ≥30-min window-gap exception and
correctly found it did not fire. **All six named `references/activitywatch.md` unprompted
and predicted its contents correctly** — lock logs as `unknown`, AFK fragments below the
threshold — working from the one-line index entry at the bottom of `SKILL.md` alone.

Arm B changed nothing. Its reps still said they would open the file "to confirm the
mechanism"; the bullet only pre-supplied a hypothesis the control arm derived by itself.

Same shape as the rejected `harvest_list.py` rule below: what the agent already gets right
from existing text needs no rule, and the index line is sufficient routing. **The 0.2.8
addition to `activitywatch.md` itself stays** — reps wanted the file to *confirm* against,
and it now states what they expect to find.

> **Amended 2026-08-12, same day, after the granularity run below.** This entry's evidence
> is weaker than "6/6" makes it sound, and the rejection should be treated as provisional.
> The fixture handed every rep three pre-computed sub-0.4 `--window` ratios, which flags the
> anomaly for them — the routing job the pointer would have done. Re-run on a fixture giving
> only the default `afk_blocks.py` output, **0 of 4 reps named `activitywatch.md`**: one
> derived the lock unaided, one said "sleep/resume", one said "watcher artifact", and one got
> it exactly backwards, treating an empty `breaks` list as affirmative evidence the user was
> never away. The pointer stays out for now because the granularity fix (below) removes the
> billing consequence, but "the index line is sufficient routing" is not established. See the
> reopened gap under Open gaps.

### "Tile the span exactly" scoped to billed sub-blocks — `SKILL.md` Step 6 guard 1
**Rung 1, measured both directions. 2026-08-12.**

On a day with no breaks, `afk_blocks.py` returns one span covering the whole day. Guard 1
said interior sub-blocks "must tile the span exactly" — so a stretch excluded under Step 3's
`<0.4` band had nowhere to go, and the span-level ratio (0.74 on the fixture) passes `≥0.7`
while hiding three nearly-dead stretches. The two rules pointed opposite ways and the doc
never said which won.

**Method.** Same fictional day as the entry above, with the pre-computed `--window` ratios
**removed** — deciding to compute them is the behaviour under test — and Step 6 guard 1
added, since omitting it was what made the earlier run's rounding results meaningless.
Correct answer 6.5 hr; the trap answer bills the whole 8.21-hr span.

**Control (guard 1 as written), 4 reps: 8.21 / 8.21 / 6.52 / 6.52.** Two reps over-billed by
1.7 hr. Reps 1 and 3 reasoned from the *same* 0.74 to opposite conclusions, which is the
definition of wording that binds nothing. Rep 1 was explicit about the mechanism: *"shrinking
an interior sub-block would break the exact tiling Step 6 requires"*, and pre-committed to
`<0.4` "not authorising me to drop it".

**Treatment (guard 1 with the tiling scope stated), 4 reps: 6.51 / 6.51 / 6.51 / 6.51.**
Unanimous, and every rep cited the scoping sentence as its reason. Baseline held: all four
still declared the ~100 min as a known exclusion and put the question to the user, none
invented a break, none silently dropped the time — so it did not trade over-billing for
under-billing.

Guard 3 already said an excluded stretch is "declared under the table and never passed to
`--cover`"; guard 1 contradicted it. Guard 1 now defers, and points at guard 3.

### Prefix → client is derived from the catalogs, not hand-listed — user `.context.md`
**Rung 2.** 2026-08-18. `.context.md` carried a hand-written prefix → client list of 12
entries with a hedge on one (`HER`→Heart Foundation "confirm vs Herman Pacific").
Deriving the mapping from `.mcp/harvest_assignments*.json` (`project.code` prefix →
`client.name`) yields **46** prefixes and contradicts the list twice: `HER` is **Herman
Pacific** and Heart Foundation is **`NHF`**; `TEP` is **EarnLearn** alone, with Connexis
under `CON`. No agent was watched misbilling on it, so rung 2 — but the hedge shows the
ambiguity was live, and a stale mapping excludes evidence silently rather than erroring.

The derivation also surfaces what the list's format could not express: **`PSO` (14
clients) and `SLA` (9) are cross-client prefixes**, so the prefix alone never identifies
the client for those two. That is the general case of the existing Technoform note that
`PSO-1037` is a dead presales shell.

`classification-rules.md` §1 step 1 sends the agent to `.context.md` for this mapping, so
the entry could not simply be deleted — it was replaced with the derivation route, which
keeps that pointer resolving.

**Rejected: keeping the list and correcting the two wrong rows.** Same defect one edit
later; the list was wrong because it was hand-maintained, not because those rows were
unlucky. **Rejected: writing the corrected 46 rows into `.context.md`.** It is 3× the
bytes of the route that generates it, against a 14,000-byte budget, and stale on the next
client.

### Environment-connected tools are a rubric signal, not only a disambiguation step
**Rung 2.** 2026-08-18. Connor asked for "XrmToolBox and similar tools carry no client in
the title; resolve from the connection string" to move into the skill. Half of it was
already there — `SKILL.md` Step 5.2 lists XrmToolBox among "generic apps that don't name
their client". But Step 5 opens `For any 🔸 block`, and Step 4 classifies against
`classification-rules.md`, whose signal hierarchy had no entry for it. **A block titled
plain `XrmToolBox` reads as unambiguous, so it is never flagged, so the Step 5.2 guidance
is never reached.** Reachability, not absence, was the defect. Added to rubric §5, which
was renamed URL pattern → *Environment identifier* to cover connections that never appear
in a title (no other file referenced §5 by name or number — §3 at line 80 is the only
cross-reference and is unaffected).

Rung 2: measured on 2026-08-17, where XrmToolBox connected to `ccamsdev` was the *first*
evidence of an NZLS→QEII switch, but no agent was watched misattributing it. That day is
also why the entry says §6's terminal-adjacency rule does not extend to these tools —
connecting to a different environment tends to *be* the switch point, so the adjacent
block is wrong by construction. Script-level behaviour is already pinned by
`test_scenarios.py::test_a_generic_tool_lands_uncategorized_rather_than_guessed`; the new
text is the classification-time counterpart and has no validator.

The client-specific half (`ccamsdev`/`ccamsuat` → QEII, `cmsdev`/`cmsuat` → NZLS) was
**deleted** from `.context.md` rather than moved: lines 23 and 55 already list those
environments under the NZLS and QEII sections, which own env → client mapping. Net −203
bytes against the Step 11 budget.

**Rejected: moving the rule wholesale into the skill as asked.** The mapping is one user's
clients; `references/context.md.example` reserves the skill for generic heuristics.
**Rejected: leaving `.context.md` as the only home.** It described a generic tool class,
so every other user of the skill would have had to rediscover it.

## Script defects

Found while building the scenario/contract suite, 2026-08-14. All **rung 1** — each was
watched failing before it was fixed, and each has a test that failed first.

### The suite was not hermetic, and one test wrote against production
`test_harvest_lookup.py` shelled out with `subprocess` to assert a non-zero exit on a
catalog miss. A subprocess inherits no fixture, so it read the real `.env` and fell
through to the live time-entries API, paging 180 days of real Harvest history — 4.7s of a
5.3s suite, and a red build whenever Harvest was slow. The same shape one flag over
(`harvest_post`) would have created a **real billable entry on a client's timesheet**.

Fixed by an autouse fixture that repoints `AW_BASE` and `API_BASE` at an unroutable
address and blanks the credential sources, plus an in-process `run_cli`. The rule —
never `subprocess` a script from a test — is in `tests/README.md`, and `test_harness.py`
asserts the guard actually blocks, because a safety net nobody tests is one nobody knows
is there.

### Two scripts parsed the same `--window` flag differently
`afk_blocks` rejected `17:00-09:00`; `activity_timeline` accepted it and printed an empty
timeline, which reads as "nothing happened then" rather than "you typed it backwards".
Same class of defect `aw_client.py` was created to end. `parse_range` now lives there and
both call it.

### `--json` did not always emit JSON
On a day with no `not-afk` activity, `afk_blocks --json` printed a sentence and exited 0.
Anything parsing the output fails on exactly the day it most needs a clean empty answer.
It now emits the normal key set with nulls; the text path keeps its sentence.

### Three CLIs crashed on import under captured stdout
`harvest_post`, `harvest_patch` and `harvest_list` called `sys.stdout.reconfigure()`
unguarded at import. Under pytest — or any harness swapping in a plain stream — that
raises `AttributeError`, which is why those three had no tests at all while
`activity_timeline` and `harvest_lookup`, which already guarded it, did. Guarded
identically.

### Bad numeric arguments produced tracebacks, not `ERR` lines
`harvest_post.py NLS-CR202 …` (a project *code* where an id belongs) died in `int()`;
`harvest_patch --hours abc` died in the flag caster. Both before any HTTP. A traceback
tells the model the script is broken and sends it debugging the tool instead of its own
argument, so both now print `ERR …` and exit 1.

### A failed request leaked its response, and the warning landed on an innocent test
`urllib`'s `HTTPError` *is* the response object — it owns a spooled temp file. Both
clients read the error body and dropped the exception without closing it, so the handle
survived until garbage collection, whose destructor then raised
`ResourceWarning: Implicitly cleaning up <HTTPError 422: …>`. Because that fires from a
destructor, it is attributed to whatever test the collector happened to interrupt, so it
read as an unrelated failure in an unrelated file. Three independent agents hit it and
each blamed a different test.

Closed in both `harvest_client.request()` and `aw_client.get()`. Worth recording for the
diagnosis more than the fix: **a failure with no plausible connection to the code it
points at is a destructor, not a mystery.**

### Zoom dropped the browser tab that was open when the zoom started
`activity_timeline --window` filtered *spans* by overlap but *web rows* by start time
alone, so a tab opened before the zoom and still open inside it vanished. That inverts
what zoom is for: the skill zooms a block precisely because it cannot tell whose work it
is, and a tab left open across the boundary — a Dataverse org, a client SharePoint — is
the row that names the client. Both filters now test overlap.

### `harvest_patch` last-won on a repeated flag and sent the request anyway
`--notes 'a' --notes 'b'` discarded the first value, exited 0, and wrote to Harvest, so
the caller believed both landed. Every sibling guard in this skill blocks *before* the
request; this one did not. Now refuses.

### From the code review, same day — nine findings, all reproduced before fixing
Each was turned into a failing test in `tests/test_review_findings.py` first; all nine
went red, so none was a false positive. Grouped by what they share: **every serious one
produced a plausible-looking wrong answer rather than an error.**

- **A dead window watcher read as an empty day.** `activity_timeline` printed a
  well-formed, entirely blank timeline and exited 0 when the window bucket was missing.
  A model reading that concludes the user did no work. Now errors, as `afk_blocks`
  already did for a missing AFK bucket.
- **The bucket preference was tested but unreachable.** `pick_bucket` prefers a
  hostname-suffixed bucket over an unsuffixed leftover, and a test covered it — but every
  caller passed a prefix ending in `_`, so an unsuffixed bucket could never be a
  candidate. On an AW that does not suffix, both scripts saw no watchers at all, while
  `references/setup.md` told a reimage-recovery reader the case was handled. Callers now
  pass the prefix without the underscore; the stale-host tie-break still wins, verified
  against the real AW, which carries both a live and a post-reimage bucket.
- **Overlapping `--cover` blocks reported over 100% coverage.** The blocks were summed
  independently. A coverage figure above the day's total activity reads as "nothing was
  missed" at exactly the moment the proposed blocks are malformed. Now unioned first.
- **Workspace auto-detection could never work on a stock install.** It walked up two
  levels from the skill — right for `<workspace>/skills/<name>`, one short of Claude
  Code's `<workspace>/.claude/skills/<name>`. Masked here only because
  `TIMESHEET_WORKSPACE` is set explicitly. Both shapes are now checked, and the "refuse
  to guess" behaviour is pinned alongside.
- **The live lookup fallback was not scoped to the caller.** `/time_entries` without a
  `user_id`; on an admin-scope PAT that pages the whole company and can surface a
  project/task the user has no assignment to.
- **`refresh_catalogs` deleted the old catalog before writing the new one**, so a failed
  write left none at all — and lookups then fell silently through to the live API. Pages
  are now staged under `.new` names and swapped in only once every write has succeeded.
- Three smaller ones: `refresh_catalogs` kept the unguarded `sys.stdout.reconfigure()`
  the other scripts had already fixed; `wait_for_project` used `.get("project", {})`,
  which returns `None` on an explicit null, against the endpoint most likely to serve a
  half-populated row; and the `pac` profile restore was skipped in silence when the
  profile list could not be read — leaving the drift it exists to prevent.

A tenth turned up while testing the ninth: `refresh_dataverse` counted lines with an
unclosed `open()`. Same family as the HTTPError leak above, found the same way.

### A test's result depended on where the checkout sat
Found by the release mirror, not by the suite. `test_edge_catalogs.py` asserted
`find_workspace() is None` as a precondition, having repointed only the cwd.
`find_workspace()` also walks `SKILL_ROOT.parents[1:3]`, so the test passed from
`~/.claude/skills/` and failed from the public checkout at
`~/Admin/activitywatch-to-harvest/skill/` — `~/Admin` is a real workspace, and the walk
resolved to it. The suite structurally could not catch this: it only ever runs from one
leg at a time, and it is `publish.ps1` running it from the *other* leg that made the
dependency visible.

Fixed by pinning `SKILL_ROOT` alongside the cwd. Every other site asserting on workspace
resolution already did this (`test_harvest_client.py`'s `isolated` fixture,
`test_review_findings.py`); the conftest `workspace` fixture needs no pin, because
`find_workspace()` consults `Path.cwd()` first and that fixture chdirs into a tree that
already contains `Timesheets/`. **A test whose precondition is "nothing resolves" has to
neutralise every source the resolver reads, not just the obvious one.**

### Three test docstrings outlived the fixes they described
Found by reading the four subagent-written `test_edge_*.py` modules line by line after
0.4.0 shipped — 95 of the suite's tests, previously audited only mechanically. All three
claims described defects fixed *in that same release*:

- `test_patch_refuses_the_same_flag_given_twice` still said "this one does not, and the
  request goes out", while its own assertion proved nothing was sent.
- `_collect_the_unclosed_error_response()` in `test_edge_harvest_api.py`, and a
  `filterwarnings("ignore::ResourceWarning")` mark in `test_edge_catalogs.py`, both stated
  that `request()` reads the error body and never closes it. It closes it — see the entry
  above. The suppression was the worse half: it blinded that test to a *future* leak.

Same shape as the `--cover` two-copies entry above, and the same lesson — **search for the
rule, not the wording.** Both fixes were written up here, in this file, while their other
copies in the test docstrings were left saying the old thing. A green suite cannot see
this class at all: a stale docstring passes every run, so only reading catches it.

The suppression is now a positive no-leak test mirroring `test_edge_timeline.py`'s
AW-side one, so a re-introduced leak fails the run instead of being ignored. Also fixed
alongside: `test_list_renders_a_missing_project_code_or_task_name_as_a_question_mark`
carried a one-case `parametrize`, covering only the both-missing shape when
`harvest_list`'s code and task fallbacks are independent, and asserted `count("?") == 2`
across the whole line — which cannot tell a missing code from a missing task.

### The rollup gives ambiguous minutes wholly to one client — pinned, not fixed
`category_rollup` credits `cats[0]`, so an event whose title matches two clients puts all
of its minutes on whichever rule AW ordered first, and the other client contributes
nothing to the totals a day's split is argued from. Found by reading, 2026-08-14: the
behaviour was already encoded in a rollup assertion, but no test or doc named it — the
shape `tests/README.md` warns about in goldens ("a golden alone would happily record a
bug"), occurring in a hand-written assertion instead.

Left as-is. The compensating control is the span: the same event sets `multi`, the span
renders `!MULTI`, and Step 4 sends the reader to investigate every one before billing.
**Splitting the minutes was considered and rejected** — a title matching two rules says
nothing about how the time actually divided, so a split is invented precision, and it
would put a plausible wrong number where a flagged one is now. Pinned by a named test
across both class orderings, so a reordering, or a change that drops `!MULTI` from the
rendering, has to confront it.

### A late flicker manufactures a second break — pinned, not fixed
`find_breaks` bounds itself by `work_end`, so when `work_end` comes from an end-of-day
blip, the preceding evening idle falls *inside* the workday and is reported as a break.
The `blip` flag next to it is what tells a reader to ignore it. Left as-is because Step 3
already routes on `blip`; pinned by a scenario assertion so a future change to either
rule has to confront the interaction.

## Rejected

- **A Step 3 pointer to the lock-screen quirk.** Measured 6/6 against a control arm — see
  the entry directly above. The reference index line already routes it.
- **Defensive handling for inputs the API cannot produce.** `harvest_list` would raise on
  a `hours: null` entry, and `harvest_lookup.lookup_from_entries` looks like it could loop
  forever. Neither is reachable — Harvest always returns a numeric `hours`, and the loop
  ends on a `next_page` of `null`. Code guarding an impossible input is code nobody can
  test and everybody has to read.
- **Validating `ENTRY_ID` in `harvest_patch`.** Nothing local can tell a valid Harvest
  entry id from an invalid one, so a client-side check adds a failure mode without
  removing the 404 it was meant to pre-empt. The id is forwarded and Harvest's answer
  surfaces as `ERR`.
- **A rule about `harvest_list.py` argument shape.** The flags `--from/--to` were
  guessed and failed; the script takes positional dates. But `SKILL.md` already
  documents the positional form in two places. The doc was right and went unread —
  adding a third statement rewards not reading, and grows the doc for nothing. What the
  agent already gets right from existing text needs no rule.
- **Global `python` → `py`.** See above.

### `afk_blocks.py` sees holes in the AFK record — script fix
**Rung 1, observed in a live run. 2026-08-18.**

`find_breaks()` filtered on `status == "afk"`; `active_spans()` split only on a recorded
afk span >= threshold. Neither ever measured elapsed time *between* consecutive events.
The watcher writes nothing at all while the machine sleeps or is locked, so an absence
leaves a hole in the stream rather than an event — invisible to the first function,
merged straight across by the second.

Live 2026-08-18 day: a 3h06m morning hole and a user-confirmed 47-min lunch produced
`breaks: (none)` and a single active span 05:16–17:28 (732 min) at a 0.48 day ratio. The
skeleton did not merely miss the breaks, it **asserted their absence** — and Step 3 says
to take the breaks list verbatim.

**Billing consequence: none on this run.** The `<0.4` band plus screenshot-gap
cross-checking excluded both stretches correctly, as the 2026-08-12 granularity fix
predicted. The cost was exactly what the first Open gap anticipated: *the quality of the
question put to the user*. The run excluded the lunch as "away" but could not name it,
and asked instead whether a break belonged in the 11:41–14:42 stretch — three hours off,
prompted by the 11:30–14:30 default lunch window. The user's correction ("i had a lunch
break around 3-4") is what surfaced the defect.

**Fix.** `insert_data_gaps()` materialises any inter-event hole >= threshold as an
explicit `GAP_STATUS` span, called once where `to_spans()` was. `find_breaks()` accepts
`("afk", GAP_STATUS)`. `active_spans()` needed no edit — its existing
`elif dur >= threshold_s` branch splits on any non-`not-afk` status once the span exists.
`break_kind()` labels each break `gap` or `afk` in the JSON and tags gap breaks in the
printout, because a watcher outage is absence of evidence while a recorded afk is
evidence of presence, and conflating them is how the empty list got inverted before.

**Tests.** Four in `test_afk_blocks.py`, each watched failing first: hole becomes a
break; hole splits the span rather than merging; sub-threshold hole does neither; gap and
recorded-afk breaks are distinguishable. The four golden scenarios moved by exactly one
added `"kind": "afk"` field each — no break count, boundary or span changed, since no
existing fixture contains a hole (verified: no golden holds a `"gap"` kind).

**The unit tests were not enough, and a mutation check is what showed it.** All four call
`insert_data_gaps()` directly, so they never exercise the one line in `main()` that puts
it in the product. Reverting that single line — gap detection built, tested, and wired to
nothing — left the suite at **266 passed / 5 skipped, fully green**, while the CLI went
straight back to `breaks: (none)` on the real 2026-08-18 stream. The original RED was also
weaker than it looked: `AttributeError: no attribute 'insert_data_gaps'` proves a function
is absent, not that the assertions discriminate a wrong implementation from a right one.

`test_cli_contracts.py::test_a_hole_in_the_afk_record_reaches_the_cli_as_a_labelled_break`
closes it end-to-end, and was watched failing against the disconnected build with a real
assertion diff (`[] != [('11:00:00','12:00:00','gap')]`), then passing once restored.
Full suite now **267 passed / 5 skipped**.

**Generalisable:** a helper-level test plus a green suite says nothing about whether the
helper is reachable from the product. Where a fix is one call site, test the call site.

## Open gaps

- **Largely closed at the data layer, 2026-08-18** (see the `insert_data_gaps` entry
  above): holes now surface as labelled breaks, so an agent no longer has to infer an
  absence from an empty list, and the inversion failure mode is gone. What remains open is
  the narrower question of whether anything routes an agent to `activitywatch.md` for the
  *sub-threshold* lock fragmentation the gap fix does not cover.
- **No scenario/golden day contains a data hole.** Now covered end-to-end by one
  `test_cli_contracts.py` case, but still absent from the scenario/golden set, so the
  hole shape is untested against the full day-shape output. The obvious next fixture.
- **ORIGINAL: does anything route an agent to `activitywatch.md` when the anomaly is not
  pre-flagged?** On the de-hinted fixture, **0 of 4** reps named it, and one inverted the
  meaning of an empty `breaks` list outright. The granularity fix removes the *billing*
  consequence — all 4 treatment reps excluded the stretches correctly without ever
  identifying screen lock — so this is no longer urgent, but the rejection above rests on a
  fixture that did the pointer's work. Before re-testing a pointer, decide what it would buy
  now that the money is safe: probably only the quality of the question put to the user.
- **Rounding is untested, not defective.** The earlier 0.75/1.00/"won't round" spread came
  from a fixture missing Step 6 guard 1. With guard 1 present, all 8 reps of the second run
  declined to round at all and reported informational durations — which is what guard 1 asks
  for. No defect visible; no test designed specifically for it.
- **The script suite has no fixture for the Dataverse leg of `refresh_catalogs.py`.** It
  shells out to `pac`, so testing it for real means an auth profile and a live org; only
  the "unconfigured, so skip before touching pac" branch is covered.
- **Screenshot capture is tested only at its seams** (`order_monitors`,
  `resolve_screenshots_dir`). `take_screenshots` needs `mss` and a display, so nothing
  covers a capture actually happening — which is the failure the 2026-08-11 entry above
  was about.
- **Every result in this file comes from one fixture** (a fictional two-client day with three
  lock-shaped stretches). It exercises breaks/idle/attribution and nothing else. Backfill,
  meetings, support tickets, and single-client days are unmeasured.
- The earlier three `SKILL.md` changes (interpreter, capture-health, skeleton freshness)
  remain unvalidated against a control.
- The Step 8 skeleton-freshness line is rung 2 and may be unnecessary; it has a
  deletion condition written into its entry.
- `tests/` has no coverage asserting `SKILL.md`'s *behavioural* claims, and by the
  method above it never usefully will — don't add doc-behaviour assertions there.
