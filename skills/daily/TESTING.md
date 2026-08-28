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

### One date per session, `/clear` between days — `SKILL.md` Step 12
**Rung 3, user-directed.** 2026-08-19. Connor asked for it outright, so it goes in
without a test arm; recording the grade honestly because the rung matters if anyone
later wonders whether it earned its place.

What *is* measured is the input cost — a run loads a timeline, a screenshot index, the
catalogs and often several PNGs, and `SKILL.md` Step 2 already names the full timeline
as "the main cause of context bloat". What is **not** measured is the failure the step
claims: a second day inheriting the first day's blocks, client mix and resolved
ambiguities as if they were evidence. Nobody has watched that misattribution happen.

The step is written around contamination rather than cost on purpose. Cost alone argues
for `/compact` (cheaper, keeps the thread), and `/compact` is exactly the option that
preserves the previous day's *conclusions* — so a cost-framed rule would recommend the
weaker reset as if it were equivalent. Framing it as contamination is what makes `/clear`
the default and `/compact` the fallback, which is the order asked for.

**Test to promote or drop it.** Two arms on a two-client backfill: one fresh agent per
day, versus one agent doing both days in sequence. Compare the second day's attributions
against the known answer. If the carry-over arm matches, the step is costing a reset it
does not need.

**Review findings, same day.** Two subagent arms (correctness, economy) read the first
draft. Both independently found that **Step 10 was a third copy of the rule and had been
left contradicting Step 12** — Step 10 told the agent to name the next date, Step 12
forbade naming it before the reset ask, so an agent reading in order violated Step 12 two
steps before reaching it. `self-development.md`'s duplication table exists to catch exactly
that, and the row added in the same edit listed two copies, not three. **The table is only
as good as the search that populates it:** grepping for the rule's wording found Step 1;
finding Step 10 needed a search for the *moment* the rule governs.

Four more from the correctness arm, all fixed: the gate was defined through "Step 9
posted", which never becomes true on a declined post or a "review today's work" run; the
draft's `<N>` remaining-days count is unknown on any date-specified run; Step 1's existing
"ask only when several prior gap days compete" contradicted the new "take the oldest";
and a deliberately partial day re-enters the gap list, so it needed an explicit carve-out
from "next day". The economy arm cut the draft 45% and was right that the contamination
argument belonged here rather than in `SKILL.md` — including one sentence ("the cheapest
way to mis-attribute a whole day") that stated as fact in the operating doc what this
entry grades rung 3. **A rung-3 claim asserted flatly in `SKILL.md` while its own record
file says nobody has observed it is a contradiction across the pair**, not just an
overclaim in one file.

**Rejected: making the reset unconditional.** On "all caught up" there is no next day to
protect, and asking for a `/clear` the user has no use for trains them to ignore the ask
on the run where it matters.

### Three-rep live test of Step 12 — `SKILL.md` Steps 1, 8, 12
**Rung 1 for two findings, rung 2 for the rest.** 2026-08-19. Three fresh agents, same
undigested prompt ("do my timesheet for yesterday"), real workspace and real
ActivityWatch, told only that no Harvest write would be approved. None was told Step 12
existed or what was being measured. Harvest was hashed before and after: five entries on
2026-08-18 unchanged, none created.

**What bound.** 3/3 asked the user whether other days were outstanding instead of running
an unrequested Harvest sweep — the bullet added for the date-specified case, where the gap
list is never built. 3/3 reached Step 12 with nothing posted, confirming the widened gate
("nothing left to post") is reachable where the original "Step 9 posted" was not. 3/3 left
the next date unnamed at Step 10.

**What did not bind: today-in-progress.** 1 fired the `/clear` ask for today-so-far, 1 said
nothing about resetting, 1 hedged it against days it had not checked. Three confident
readings of one input is the definition of wording that does not bind. Step 1 says today is
in progress and "not a reason to ask"; Step 12 says ask whenever days remain; nothing said
which governs. Fixed by naming the answer — today-so-far *is* a next date, and Step 1's
clause is scoped to date *selection*.

**The re-invoke clause survived 1/3.** It was prose inside a paragraph. Agents compressing a
closing message drop the tail of a paragraph and keep bullets, so it is now a bullet.
Dropping it matters more than it looks: `/clear` unloads a skill that cannot re-invoke
itself, so a reset without the reminder is worse than no reset.

### A dated run never checked whether the date was already billed — `SKILL.md` Step 1
**Rung 1.** 2026-08-19. Found independently by all three agents above, unprompted, and
called the run's worst defect by each. Step 1 swept Harvest only on a *no-date* run; given
"yesterday" it went straight to Step 2. All three loaded the skeleton, the categorised
timeline and a ~700-file screenshot index before discovering the day was finished. One
caught it only by widening the credentials probe on a hunch.

**Why no guard caught it:** Steps 3, 6 and 8 all validate the proposal against
ActivityWatch. Not one compares it to Harvest, so a duplicate day passes every check in the
file and double-bills the client. `--cover` would report clean, because the blocks are
*correct* — they are just already posted. Only the test's no-post rail prevented it.

Fixed at Step 1 (check before loading anything) with a restatement in the Step 8 checklist,
since Step 8 is the last gate before a write. `Timesheets/<date>_harvest_responses.json` is
named as the free done-marker that was sitting there unread.

**This is the shape to watch for:** a guard family that all measures against one source is
blind to errors in the other, however many guards there are.

### A settled window gets re-litigated on recomputed evidence — `SKILL.md` Step 1

**Rung 1.** Observed in production 2026-08-28, on 2026-08-21. A prior session's August audit
proposed deleting entries `2995286924` (1.50h) and trimming `2994441296` — both on `active_ratio`
(0.12 and 0.38) plus screenshot reads. Both entries exist *because Connor asked for them* on
2026-08-25 after querying the day total, as user-attested AI knowledgebase work the tooling cannot
see. `2026-08-21_harvest_responses.json` records that instruction and says in terms: "THE ACTIVITY
RATIO DOES NOT GOVERN THAT ENTRY: do not trim it on a <0.4 argument." The proposal re-ran precisely
that argument. Caught at the confirmation gate; nothing was deleted.

**Two failures, one paragraph.** The file was named at Step 1 only as "a free done-marker", which
teaches an agent to test its *existence* and never open it. And nothing said that a decision already
taken binds — so recomputing the ratio felt like new evidence when it is the same argument on the
same data. Both halves are now in the already-covered branch; the `:82` mention points at it rather
than restating.

**Why "read it whole" and not "read its `declared_judgments`".** The schema is ad hoc — across 46
files on this machine the rulings live under `exclusions`, `notes`, `note`, `excluded`,
`judgment_calls`, `declared_judgments`, `attribution_notes`, `tail_note`, `unbilled`, and one-off
keys invented per run. No key name can be the rule. Same shape as Prerequisite 1's `.context.md`
rule, and worded to match it.

**Second occurrence of this shape in eight days.** `2026-08_audit_corrections.json` withdrew a
2026-08-17 over-billing finding as a false positive on 2026-08-28, lesson recorded as "screenshots
answer WHICH CLIENT, not how long."

**Fix untested — post-fix fresh-agent arms not run** (subagents were not authorised in the session
that made the change). The rung-1 evidence establishes the failure, not the repair.

### The already-covered branch subtracts without loading the rubric — `SKILL.md` Step 1, folder mechanics

**Rung 1.** Same 2026-08-21 incident. Both proposals cited single-monitor captures as evidence of a
dead window: `13-15-01_m1` (wallpaper) for the 12:30-14:00 delete, `11-55-01_m1` (black) for the
trim. Reading `_m2` at the same instants refuted both — ChatGPT with a typed, unsent prompt about
the `github-llm-wiki` skill, and VS Code "Admin" with `auto mode on · ← 1 agent` and live agent
output. `.context.md` flags that exact agent-supervision pattern *for that date*.

**The rule was not missing.** `classification-rules.md` § "Focused window ≠ active attention"
already says to read the other monitors before shrinking a thin block or dropping a stretch on ratio
alone, and says it well. The defect is routing: the already-covered branch deliberately skips
`classification-rules.md` (measured — see "The already-covered branch verifies time, never
classification"), which is correct while verifying and wrong once the branch starts subtracting.

**Rejected: a fourth copy of the monitor rule in `SKILL.md`.** That is the fragmentation defect —
a rule spread across places, none complete. Fixed as routing (reductions pull in the rubric) plus
one scope repair: the folder-mechanics line licensed checking other monitors only "when hunting a
client signal", which still permits the single-monitor read that caused this. Widened to cover "is
anything happening at all", with `classification-rules.md` kept as owner. Both pairs added to
`self-development.md`'s drift table.

**Fix untested — post-fix fresh-agent arms not run.**

### Timesheet-admin time gets back-billed onto real work — `classification-rules.md`
**Rung 1.** 2026-08-19. On 2026-08-18, 17:30-17:54 was posted as internal timesheet admin,
non-billable. Four screenshots across that window (17:31/17:39/17:46/17:51) show client
access-sync work — `design.md` on the retry-backoff note, terminal on intake libraries,
Power Apps on the SOW15+SOW05 solution — and no Harvest or timesheet surface on any of the
three monitors through 18:06.

Structural, not a one-off: the timesheet run necessarily happens *after* the last block it
can bill, so there is no live block left to put it on and it lands on the previous one. The
client loses the time silently, and it looks plausible on review because timesheet admin
genuinely did happen that evening. Rule added: read a capture inside the window and confirm
a timesheet surface is actually on screen before booking timesheet-admin time.

### `--window` reprinted the whole day skeleton — `afk_blocks.py`
**Rung 2.** 2026-08-19. Raised by two of the three agents unprompted. Step 3 validation asks
for a ratio per thin stretch, so a careful run makes three or four `--window` calls and pays
for three or four whole-day dumps of a skeleton it already loaded in Step 2. A bare
`--window` now prints the header, the `work_end`/blip/tail warnings and the ratio, dropping
the breaks and active-spans lists. `--cover` and `--json` are untouched, and no golden
covers the `--window` text path — only its `ERR` case and its JSON.

### The "Files in this skill" list is hand-maintained and had drifted — `SKILL.md`
**Rung 2.** 2026-08-19. Found by a subagent arm pointed at the tooling rather than the
prose, during the Step 12 review. The list omitted `scripts/aw_client.py` — a real runtime
import of both `afk_blocks.py` and `activity_timeline.py` — plus `VERSION`, `tests/` and
`pytest.ini`. The public `README.md` directory tree *did* list `aw_client.py`, so the
skill's own copy was the one that drifted.

Nothing catches this. The installers and both mirror scripts copy whole trees with pattern
exclusions (`robocopy /E`, `rsync --exclude`), so a new file always ships — which is the
good version of the defect `self-development.md` warns about, and the reason the drift was
invisible for so long: the list is decorative to the tooling and load-bearing only to a
reader. `test_references.py` validates `python scripts/<name>.py` *commands*, not this list.

**Not fixed by a gate, deliberately.** A test asserting the list matches `ls` would have to
encode which files deserve a description, and the list's value is the descriptions, not the
names. Re-check it by eye whenever a script is added; that is the whole procedure.

### An exclusivity claim survived in `classification-rules.md`
**Rung 3.** 2026-08-19. `references/classification-rules.md` § "Task selection" opened with
"**This table is the single authoritative mapping** — `SKILL.md` does not carry its own
copy". The claim was *true* when checked, which is exactly why the shape is banned: it
enforces a snapshot, and the next edit that adds a pointer elsewhere rots it silently while
it still reads as authoritative. Reworded to name the owner instead ("This table owns the
activity → task mapping; `SKILL.md` Step 4 points here rather than restating it"), which
survives someone adding a second pointer.

Predates the rule that forbids it — `self-development.md` acquired the prohibition later
and nobody swept the existing files for the pattern. **Writing a rule does not retrofit
it.** A `grep -rn` for the shape across the whole skill is what found this one, and now
returns only the rule's own statement of itself.

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
entries with a hedge on one (`NIM`→Harbour Foundation "confirm vs Nimbus Pacific").
Deriving the mapping from `.mcp/harvest_assignments*.json` (`project.code` prefix →
`client.name`) yields **46** prefixes and contradicts the list twice: `NIM` is **Nimbus
Pacific** and Harbour Foundation is **`HRB`**; `LRN` is **Ledger Learning** alone, with Beta
Industries under `BET`. No agent was watched misbilling on it, so rung 2 — but the hedge
shows the ambiguity was live, and a stale mapping excludes evidence silently rather than
erroring.

The derivation also surfaces what the list's format could not express: **`PSO` (14
clients) and `SLA` (9) are cross-client prefixes**, so the prefix alone never identifies
the client for those two. That is the general case of the existing note that
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

Rung 2: measured on 2026-08-17, where XrmToolBox connected to `beta-dev` was the *first*
evidence of an ACME→BETA switch, but no agent was watched misattributing it. That day is
also why the entry says §6's terminal-adjacency rule does not extend to these tools —
connecting to a different environment tends to *be* the switch point, so the adjacent
block is wrong by construction. Script-level behaviour is already pinned by
`test_scenarios.py::test_a_generic_tool_lands_uncategorized_rather_than_guessed`; the new
text is the classification-time counterpart and has no validator.

The client-specific half (`beta-dev`/`beta-uat` → BETA, `acme-dev`/`acme-uat` → ACME) was
**deleted** from `.context.md` rather than moved: lines 23 and 55 already list those
environments under the ACME and BETA sections, which own env → client mapping. Net −203
bytes against the Step 11 budget.

**Rejected: moving the rule wholesale into the skill as asked.** The mapping is one user's
clients; `references/context.md.example` reserves the skill for generic heuristics.
**Rejected: leaving `.context.md` as the only home.** It described a generic tool class,
so every other user of the skill would have had to rediscover it.

### The already-covered branch verifies time, never classification — `SKILL.md` Step 1

**Rung 1.** Three fresh agents, 2026-08-19, identical undigested prompt ("do my timesheet
for the 18th") against 0.4.8, hard no-write constraint. The 18th was already fully billed
and contained a known bad entry: `2991009175`, 17:30-17:54, 0.40h on `NWC-001 Billing -
Timesheet & Exp`, while every capture across the window shows client access-sync work.

**2 of 3 reported the day holds.** Both followed the branch exactly and both said in their
own logs that they had deliberately skipped the screenshot index and
`classification-rules.md`, because the branch asks for `--cover` plus the `<0.4` band and
nothing else. Both are *time* checks: an entry with the right clock and the wrong project
passes `--cover` perfectly, so the branch could not see the defect it was pointed at. The
third agent found it only by departing from the branch, and reconstructed the mechanism —
the draft visible on screen at 17:49 proposed four entries ending 17:30 with no `NWC-001`
line, so the admin entry was added after that and back-dated.

This is the "one rule for all operations" mistake. `classification-rules.md` required a
screenshot check before **booking** timesheet-admin time; nothing required one when
**verifying** an entry that already existed. Both copies now name both operations.

**Rejected: making the verify branch re-read the whole day.** That is redrafting, which the
branch exists to avoid. The check is scoped to non-billable and internal entries — the ones
whose failure mode is moving time off a client.

**Re-run after the fix, same prompt, three fresh agents: 3/3 caught it** (from 1/3). All
three read captures inside the window unprompted, all three found no Harvest surface on any
monitor, all three proposed the same `harvest_patch.py` repoint and stopped at the
confirmation gate. Two independently noticed that the entry is the same one already written
into the rubric as a worked example — the lesson had been captured and the entry never
corrected.

**Step 12 fired on 1 of the 3 re-run reps, and that is the gate working, not a regression.**
Before the fix the run ended with nothing outstanding, so all three asked for `/clear`. After
it, the run ends holding an unexecuted correction — a Harvest write *is* in scope and has not
happened — so "the date is done when nothing is left to post" is false and Step 12 correctly
does not fire. The one agent that did ask for the reset asked while its own patch proposal was
still open. **No rule was added for this**: the two agents that stayed silent were following
the existing gate correctly, and a rule for behaviour that is already correct is the thing
this file exists to prevent.

### The same three reps, on everything else — 0.4.8 held

**Rung 1.** Scored by hand from each agent's full tool log. 3/3 checked Harvest before
loading the skeleton; 3/3 read `.context.md` whole with no grep or partial read; 3/3
verified instead of redrafting, so no duplicate day was proposed; 3/3 asked whether days
remained rather than running an unrequested sweep; 3/3 attached the `/clear` ask. Harvest
was confirmed unchanged before and after — same five entry ids, today still empty.

**The re-invoke instruction went 1/3 → 3/3** when it moved from prose into its own bullet,
which is the measurement behind that bullet's existence. Agents compressing a closing
message keep bullets and drop paragraph tails.

### Two defects in the 0.4.8 text itself, found by re-reading what shipped

**Rung 2.** Step 8's checklist line read "this is the only one that would catch a duplicate
day" — an exclusivity claim, written in the same change as the `self-development.md` rule
forbidding them, and the fourth time that shape has been committed while the rule was in
context. The first grep for it missed it because the pattern searched for "the only
place/file" rather than the shape; a broadened pattern (`the only`, `nothing else`, `no
other`) is what caught it. Use the broad one.

Step 12 carried "(Three test agents split 2-1 on this sentence when it was absent.)" — a
test record in the operating doc. Moved here. `classification-rules.md`'s "Observed on
2026-08-18" line was **kept**: it is a recognisable worked example of the failure, not test
methodology.

### Step 11 had no bucket for "the bundled script is wrong" — 0.4.10

**Rung 1.** 2026-08-19. Two measurements, and the first one was mine to throw away.

**Run 1 was contaminated; do not cite it.** Five raw findings from the 2026-08-18 runs,
three fresh agents, full filesystem access. Two defects in the fixture:

- The prompt said *"if a note doesn't fit anywhere the skill offers, say so explicitly
  rather than choosing the closest option."* That is the answer to the question being
  asked. An agent replying "this fits neither bucket" was echoing the prompt.
  `changing-agent-instructions` warns that a test's constraints can manufacture a gap;
  here they manufactured the fix.
- One finding was the Step 1 verify-branch blindspot, closed in 0.4.9 that morning. All
  three correctly reported it already fixed, which measures nothing about the upstream
  path.

Salvageable from run 1, because the destination was *not* supplied by the prompt: on the
`uncategorized` ADO board, all three routed to `references/setup.md` § categories,
unprompted and identically, and two diagnosed the live regex fault themselves. **A "the
machine, not a document" bucket was drafted for Step 11 and then dropped on this
evidence** — Step 2 already says maintenance gets noted and raised at Step 11, and the
agents already follow it. See Rejected.

**Run 2 is the measurement.** Neutral closing instruction, no filesystem access, fictional
consultant who installed the skill from GitHub and has no checkout, and a defect the
current docs genuinely do not cover (`activity_timeline.py` double-counting spans both
watchers saw — 11.4 h categorised against a 7.2 h day). Three reps:

| Behaviour | Reps | Consequence for 0.4.10 |
|---|---|---|
| "Step 11 has no bucket for the bundled script being wrong" | 3/3 | The gap is real. One bullet added. |
| Proposed reporting upstream unprompted | 3/3 | The route needs no rule; none written. |
| Refused to file under any circumstances | 3/3 | **Inverted from the assumption.** Agents are stricter than the chosen gate, so the rule *permits* filing behind an explicit yes rather than restraining it. |
| Looked in `self-development.md` for the upstream route | 3/3 | The filename mis-signals. Pointer added there. |
| Could not produce the repo URL | 2/3 | Not derivable from an installed skill. Stated in the reference. |
| Refused to park a generic rule in `.context.md` | 3/3 | Already correct. No rule. |
| Flagged that a local patch is reverted by the next install | 3/3 | Already correct. No rule. |
| **Mentioned redaction, or client data in a public issue** | **0/3** | The real gap. Two drafted full issue bodies off a client timesheet run without one word about stripping client identifiers. |

So `references/reporting-issues.md` earns four things and nothing else: the repo URL,
redaction, permission to file behind a gate, and the `self-development.md` misdirection.
Everything else in its first draft was behaviour all three reps produced unprompted, and
was cut before shipping.

**Run 3 — the same fixture against 0.4.10.** Three fresh reps, same no-tools discipline,
now reaching the new Step 11 bullet and `reporting-issues.md`.

| | Run 2 | Run 3 |
|---|---|---|
| Sorts to the third bullet and forks installed-vs-maintains | no bullet existed | 3/3 |
| Produces the repo URL without asking the user | 1/3 | 3/3 |
| **Redacts** | **0/3** | **3/3** |
| Asks for a yes to *filing*, distinct from agreeing the defect is real | 0/3 would file at all | 3/3 |
| Falls back to a saved draft rather than improvising a route | n/a | 3/3 |
| Keeps the defect out of `.context.md` | 3/3 | 3/3 |
| Declines to patch the installed script | 3/3 | 3/3 |

Convergence is on *behaviour*, not wording — three different issue titles, three different
body structures, three different orderings. Two reps independently added the right answer
to a case the text doesn't cover: if `reporting-issues.md` were missing from an install,
tell the user the route isn't documented in their copy and report that too, rather than
falling back to `self-development.md`, which disclaims the path.

One rep added a `gh issue list --search` duplicate check and flagged it as its own idea.
1/3, rung 3. **Not written in** — one rep reaching for something is not evidence a rule is
needed, and the reference is already at the length where every line has to earn itself.

### An exclusivity claim, written while writing the rule against them — 0.4.10

**Rung 1.** 2026-08-19. `reporting-issues.md` shipped a draft reading *"so this is the only
place to read it from"* about the repo URL. The broad grep
(`the only (place|one|file|section)|nothing else|no other`) caught it, and it was **also
false** — `TESTING.md` and `tests/test_edge_catalogs.py` both name the repo. Second
occurrence of this shape in two releases, both times in the same change as the rule.
The grep is the control that works; the rule alone is not.

### `gh issue create` ships unexercised — 0.4.10

**Rung 3.** 2026-08-19. GitHub was unreachable from the machine for the whole release
(`github.com` and `api.github.com` both time out; Harvest answers in 0.54 s), so the filing
half is documented and never run. The drafting, the gate and the triage were measured; the
command was not. First reachable session: file one real issue and confirm the flags.

### A long browser window row is not one unit of work — `classification-rules.md` §5

**Rung 1 on both failures. 2026-08-24. Not tested against a control.**

Measured on the 2026-08-21 run, and the paragraph was rewritten the same day after the second
failure. A 124.7-min `msedge.exe | ChatGPT and 8 more pages` window event sat at
`uncategorized`. Inside it, the web-watcher rows named two clients, the second surfacing about
a minute before the event ended; screenshots later showed an 85-minute Teams call had been
running on a different monitor for the event's whole length.

Both failures were real and they pull in opposite directions, which is why the paragraph
covers both. **First:** the run billed the whole span to the dominant client, reading the long
row as one unit of work. **Second:** told to fix that, the run split the span at the brief
second-client tab hits — which were 30-second checks made *during the call*, not a switch —
and trimmed a client's entry on the strength of them. A paragraph that had said only "treat a
lone web row as a possible switch point" would have endorsed the second error, so it now says
a lone row is a lead to check against the other monitors, and adds that a thin `active_ratio`
under a long browser row can be a call rather than idle.

**What was not measured.** No agent was watched attributing a long browser event either way,
and the 3-rep control in the Rejected entry below found the switch point *without* this
paragraph, so it is not credited with that. Its second half overlaps §3's "Focused window ≠
active attention", deliberately: §3 owns the mechanism, and this states the browser-row
symptom that should send a reader there. If a later round needs bytes back, test whether the
§3 pointer alone suffices before keeping the restatement.

### Setting precedence, and blank-counts-as-unset — `scripts/skill_config.py`
**Rung 3.** 2026-08-28, issue #5. Configuration reached the scripts from three sources
with no stated rule about which won, and each script merged the subset it cared about its
own way: `load_creds()` re-walked `.env`-then-OS-env alongside `config()`, which already
did it; `screenshot_capture` layered `argv[0]` on top by hand; `harvest_lookup` layered
`--mcp-dir` on top differently. `skill_config` is now the reader, and `test_config_seam.py`
fails if a second one appears in `scripts/`.

**Two decisions worth not re-litigating.**

*`.env` still beats the process environment.* That is the order as it has always behaved.
It is the wrong way round for a harness that injects settings as environment variables —
a stale `.env` will outrank what the harness supplied — but flipping it changes which of a
user's two configured values wins, and a prefactor whose whole claim is "nothing
observable changes" is the wrong place to do it. The flip belongs with the ticket that
introduces the injection, and the seam is what makes it a one-line change.

*Blank now counts as unset at every layer, which is a deliberate widening, not a pure
move.* `_parse_env_file` already stripped, so a blank in `.env` never reached a caller;
a whitespace-only **environment variable** did. Preserving that exactly would have meant
two different truth tests inside the one module that exists to hold one rule. The
behaviour it changes: `HARVEST_API_KEY="   "` exported in a shell used to reach Harvest
and 401, and now exits `ERROR: Harvest credentials not found.`; `DATAVERSE_URL="  "` used
to attempt the Dataverse refresh and now skips it with the documented notice. Both new
answers are the ones `.env.example` already promised ("leave blank if you don't need
them"). The golden days are unaffected — neither AW script reads a setting.

**What was not measured.** No agent was watched getting the old precedence wrong; the
duplicate reader was found by reading, not by a failure. The suite is evidence only that
the move changed no behaviour the tests cover, which for the AW scripts is the whole
golden set and for the Harvest ones is the recorded request bodies.

### Workspace resolution is anchored on the install shape, not on a depth
**Rung 1.** 2026-08-28. Supersedes "Both shapes are now checked" in § "Script defects"
below, and owns the rule the two install-shape tests in `test_config_seam.py` pin.

`find_workspace()` walked `SKILL_ROOT.parents[1:3]` — two arbitrary ancestors — and took
the first that held `.mcp/` or `Timesheets/`. That is not "two shapes checked", it is *any*
ancestor at either of two depths accepted, and the difference is the whole defect: an
install nested one level deeper than either shape resolves to whatever real workspace
happens to be above it. Already observed once — see § "A test's result depended on where
the checkout sat", where the public checkout inside `~/Admin` resolved to `~/Admin`.

It now requires the skill to sit directly inside a `skills/` directory and takes that
directory's parent, skipping Claude Code's `.claude/`. A plugin install is the shape that
forced the rule rather than a third depth: `<plugin>/skills/<name>` matches the first shape
exactly, while the directory above the plugin is the harness's plugin cache or whatever a
clone sits inside. The plugin holds no user data, so `.claude-plugin/` beside the skills
directory means "not a workspace, stop".

**Why this needed its own test rather than a green run.** The wrong answer is silent and
delayed: the refresh reports success, writes catalogs where no lookup reads them, and the
staleness surfaces days later as a bad classification. The suite could not catch the
original because it only ever ran from one leg at a time; the release mirror caught it.
With the mirror going away, the pinned tests are what replaces it.

**What was not measured.** No agent was watched acting on the stale catalogs. The
consequence — refresh writes to a directory the reader never opens — is arithmetic on the
resolver, not an observation.

**Cost, accepted.** A plugin install now resolves *no* workspace, so `TIMESHEET_WORKSPACE`
has to be set. That is correct rather than convenient — the alternative is guessing. It is
no longer a cost the user has to discover: the install asks for the workspace directory as
a declared optional option — see the next entry.

### The configuration surface is declared, and the New Zealand offset is gone
**Rung 1.** 2026-08-28. Issue #7.

Six settings are now declared in `.claude-plugin/plugin.json` under `userConfig`, so a
fresh install asks for them once. Three platform facts were verified against the installed
CLI rather than reasoned about, because each one would have been wrong to assume:

1. **Non-interactive form.** `claude plugin install <plugin>@<marketplace> --config KEY=VALUE`,
   repeatable, with `-y`. There is no `claude plugin config` subcommand — the first guess.
2. **Where sensitive values land.** A non-sensitive option appears in `~/.claude/settings.json`
   under `pluginConfigs`; a `sensitive` one does not appear there at all. That flag is the
   entire mechanism for keeping a token out of a file — there is no second one to also set.
3. **Whether a `directory` field validates the path.** It does not: `C:/does/not/exist/at/all`
   was accepted and stored. So `references/setup.md`'s reimage note still stands — a
   configured workspace path is checked by nobody, and a stale one breaks catalog lookups
   silently while Harvest-only scripts keep working and mask it.

Two further findings, both load-bearing:

- The `CLAUDE_PLUGIN_OPTION_*` variables reach **hook processes only**, never the shell the
  model runs scripts in. `hooks/publish_plugin_config.py` bridges that at SessionStart via
  `$CLAUDE_ENV_FILE`, so the values arrive in the layer `skill_config` already documents as
  "the process environment, which is where a harness injects values". No new precedence.
- A manifest `default` on an option the user never set is **not injected** — it is a dialog
  pre-fill only. So the real fallback for an optional setting stays the script-side
  `setting(..., default=...)`, and a `default` in the manifest would be a value shown to a
  user as though it were the considered answer for them while changing nothing.

**The defect this closes.** `--utc-offset` defaulted to `12.0` in both scripts. Every user
outside New Zealand got a day boundary up to twelve hours out, and *nothing failed*: events
landed on the wrong date, the timesheet was filed against the wrong day, and the only
symptom was a day that looked oddly short. It is now resolved from `TIMESHEET_TIMEZONE` at
the date being analysed, and a run with neither that nor `--utc-offset` refuses. Refusing is
the answer rather than a better guess: there is no offset that is right to assume.

**Cost, accepted.** `zoneinfo` is stdlib but its data is not shipped with Python on Windows,
so a machine without `tzdata` cannot resolve a zone. That is reported as an explicit error
naming both `pip install tzdata` and the `--utc-offset` escape hatch — never a silent
fallback, which is the failure mode being removed. The stdlib-only rule holds for the
scripts themselves; the zone database is data, and its absence is now a message rather than
a wrong answer.

**What was not measured.** No user was watched completing a fresh install through the
dialog. The acceptance criteria about prompting are asserted against the manifest
(`tests/test_plugin_config.py`), which is what the dialog is generated from.

**Known limitation: the session hook needs a POSIX shell.** Confirmed from the shipped
binary, not assumed — it selects PowerShell for hook commands on Windows when Git Bash is
absent, and warns specifically about PowerShell hook commands. The manifest's command is
`sh "${CLAUDE_PLUGIN_ROOT}/hooks/publish_plugin_config.sh"`, so on such a machine the hook
never starts and the user gets "I configured everything and nothing is configured".

Three fixes were considered and rejected before accepting the gap:

- *Name the interpreter directly* (`python3 …`, exec form, no shell). No single token
  works everywhere: `python3.exe` is absent from a python.org install on Windows, and `py`
  does not exist on POSIX.
- *One hook entry per shell.* The one that cannot spawn prints an error to the user at
  **every** session start on the other platform — trading a silent failure for permanent
  noise.
- *A shell polyglot.* Unreviewable, and this file argues against exactly that kind of
  cleverness elsewhere.

So the gap is closed by diagnosis rather than by mechanism: both "missing setting" messages
name a new session first and `references/setup.md` § "When the configuration does not
arrive" second, which carries `winget install Git.Git`. That section also carries the other
cause, found in the same review — a `.env` left over from a copied-in install now outranks
`/plugin configure`, because for the first time both routes carry the *same* keys and the
seam puts `.env` above the process environment. The precedence itself was not changed here:
reordering which of a user's two configured values wins is not something to do inside a
ticket about declaring the surface.

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
`harvest_post.py ACM-CR202 …` (a project *code* where an id belongs) died in `int()`;
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
  to guess" behaviour is pinned alongside. **Superseded 2026-08-28** — widening the walk to
  two depths was itself the next defect; § "Settled decisions" → "Workspace resolution is
  anchored on the install shape, not on a depth" replaces it.
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
resolution already did this (the `isolated` fixture, since moved with the settings reader
into `test_config_seam.py`; `test_review_findings.py`); the conftest `workspace` fixture
needs no pin, because
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

### `--ponumber` doubles the synced Harvest project name — rung 1, observed

Creating ACM2252S with the work-item reference in *both* the title and `--ponumber` produced
the Harvest project name `Case BAU backlog - … (US1240, US1242) US1240, US1242`. The sync
appends the PO value to the name, and that name is client-facing. Instruction added to
`references/new-client-work.md`: put the reference in one field or the other. Not measured:
whether editing the case title afterwards re-syncs the project name, or whether the name is
only set at creation — so the entry does not tell anyone to fix it that way.

Second observation from the same case, recorded but not acted on: the synced project came
back `hourly_rate: null` / `use_default_rates: true`, so `--rate` writes the Dataverse case
field only. Whether it reaches invoicing is unverified.

### The `S` suffix does not mean Support — rung 1, observed

`create_incident.py` assigned **ACM2252S** to a case whose shape was DEVELOPMENT / BACKLOG
(`<prefix>_sla=False`, `casetypecode=1`). The trailing `S` is applied by CRM numbering
regardless of case shape, so the restated "trailing `S` = Support, tag `[Support]`" rule is
not safe on its own. Corrected in the affected user's `.context.md`; `SKILL.md` Step 4 and
`classification-rules.md` §1 still state the `S` rule without this qualification and were
left alone pending a decision on wording.

## Rejected

### Byte size as a "static screen" signal — narrowed, 2026-08-28

**Rung 2 for the half that shipped, rejected for the half that did not.**

What shipped, at the folder mechanics: a black or locked capture is ~6-7 KB, so `Length` ranks a
long screenshot index before spending image tokens. Measured on 2026-08-21. Two limits shipped with
it because both were observed the same day: a 3.7 MB file that looked substantive by size was a
detailed wallpaper photograph of seals, so size never confirms work either.

**Rejected: "near-constant sizes across consecutive captures mean a static screen."** True as
pixels and wrong as an inference. It is re-deriving active/idle from screenshots, which Step 5
forbids and the AFK watcher owns — and it was the actual reasoning behind the C2 deletion proposal
(`2994441526`, 15:08-15:55): all three monitors byte-static 15:10-15:57, therefore dead. Put to
Connor with that evidence on 2026-08-28, he kept the entry. A heuristic whose only production
outing produced a rejected finding does not belong in the instructions.

### A "check the tail of the final block" rule — 2026-08-24

**Rung 1 on the failure, and the failure was mine, not the doc's.**

A real run (2026-08-21) posted the day's last block 15:55-17:20 to one client when the
last 7 min were another client plus an internal call. The obvious conclusion was that the
switch-point protocol probes block interiors but not trailing edges, and that `SKILL.md`
Step 3 needed a sibling to its `work_end`-blip rule: *end the final block at the last
substantive evidence for its own attribution, not merely at the last active moment.*

**Control, 3 reps, current text, fictional day with the same signal shape** (one 125-min
`uncategorized` browser window event, a second client appearing only in the last 7 min at
ratio 1.0, `LockApp.exe` taking focus immediately after, and the per-user
agent-supervision note in scope). No filesystem access, so no rep could quote the real doc
back.

**All 3 found the switch point and refused to bill the tail to the dominant client.** Each
cited step 3's "a switch point is a real boundary even with no AFK gap". Two billed the
tail to the second client at the 0.25 floor and said so as a flagged judgment call; one
left it unbilled and offered the floor as the alternative. None absorbed it under step 7's
`>=15 min` noise bar, and none needed the noise bar's scope narrowed. The rule was not
written: the existing text already binds.

**A second finding from the same 3 reps — WITHDRAWN the same day. Read this part as a
lesson about the fixture, not about the run.** All three also refused the `.context.md`
agent-supervision exemption ("don't shrink a thin block on ratio alone") on the grounds
that its stated trigger — `Welcome - Admin - Visual Studio Code` + `auto mode on <- N
agent` — was absent, the focused window being a browser. Having refused it, all three
shrank the thin (0.67) block to its active minutes: 0.75 / 0.75 / 0.8 hr against the run's
1.42 hr wall-clock. That looked like a clean unanimous verdict that the run had invoked the
exemption without checking its trigger.

**It was an artifact of the fixture.** The fixture was built from window-watcher rows and
`active_ratio` slices only. Screenshots of the real day then showed a Teams call running on
monitor 1 across the whole block and `auto mode on` + `1 agent` on monitor 2 — so the
exemption's trigger *was* present, and the low ratio was a call rather than idle. The window
watcher logs only the foreground window, which is precisely the blind spot the exemption
exists to cover. By feeding the reps window rows alone, the fixture deleted the evidence the
rule keys on and then asked whether the rule applied. Three unanimous refusals were three
agents correctly reading a fixture that could not contain the answer.

**The lesson, which is the durable part.** A fixture assembled from one watcher cannot test
a rule about a second watcher's blind spot, and unanimity across reps does not detect this —
it reads as a strong signal right up to the moment someone opens a screenshot. When a rule's
trigger is *visual* (a marker on another monitor), the fixture has to carry the visual
evidence or the arm is void. `changing-agent-instructions` states the general form of this
("your constraints can manufacture a gap"); this is that failure committed while holding
that skill in context, which is worth recording precisely because knowing the rule did not
prevent it.

What survives: the tail-rule rejection in the paragraph above. That arm turned on evidence
the fixture did contain — the switch point is visible in web-watcher rows — so it stands.
What does not survive: any claim about the exemption, in either direction. It is untested.

Variance worth noting for anyone re-running this: the reps agreed on every boundary and
disagreed only on the 7-min tail's disposition (unbilled vs the 0.25 floor) and on the
untested head of the block.


### A "the machine, not a document" bucket in Step 11 — 2026-08-19

Planned for 0.4.10 and dropped before it was written. The trigger was a client's ADO board
coming back `uncategorized`, which is an ActivityWatch category rule and fits neither of
Step 11's two destinations. Three fresh agents all routed it correctly anyway — to
`references/setup.md` § categories — because Step 2 already tells a run that maintenance is
noted and raised at Step 11, not fixed mid-timesheet. Two went further and found the live
regex fault unaided. What the agent already does correctly needs no rule; adding the bucket
would have paid SKILL.md bytes on every run to restate working behaviour.


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

### Does a piece split out of a thin block re-validate at its own ratio? — untested

Surfaced by the 3-rep control in `## Rejected` ("a check the tail of the final block rule"),
2026-08-24. Step 3's thin band (0.4-0.7) says to shrink to the contiguous active spans and
re-merge so the entry's duration is approximately the summed active minutes. It does not say
whether the shrunk piece is then re-validated at *its own* `active_ratio` — and the two
readings diverge materially.

Arithmetic instance (2026-08-21, and see the caveat below before using it as a case): a
block measured 0.64 across 15:55-17:13 with 49.6 active min, whose head 15:55-16:57 is
**0.73** on its own — the `>=0.7` band, which bills wall-clock (1.03 hr) — while its tail
16:57-17:13 is 0.28. Duration-approximately-active-minutes instead gives 0.75 hr. The gap is
0.28 hr on one entry, so the two readings are not interchangeable.

All three reps took the summed-active-minutes reading, but none was in a position to do
otherwise: the fixture handed them 20-min slices and never showed a shrunk piece's own ratio.
So the reading is unanimous and uninformative on the question.

**Caveat on that instance — it is arithmetic, not a worked example.** Screenshots later
showed the block was a Teams call with an agent running alongside, so under the exemption it
should not have been shrunk at all and neither candidate reading applies to it. The
divergence it illustrates is real and the numbers are real; the block is the wrong case to
settle it on. Whoever runs the control should build a fixture where the thin band genuinely
governs — no meeting, no agent marker on any monitor — and must carry per-monitor evidence
so the exemption can be seen to be absent rather than merely omitted (see the withdrawn
finding in `## Rejected`).

Not resolved here, because picking a side without a control is the untested-diagnosis move
this file exists to prevent.


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
