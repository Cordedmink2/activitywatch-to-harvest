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

**Superseded** by §"The 'Files in this skill' inventory had lost eleven flags — #26": the
eye missed it again, this time losing flags rather than files. There is a gate now, over
the names and the flags only. The reasoning above still holds for the descriptions, which
it does not touch.

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

**Amended 2026-08-31, issue #11: `.agents/` is skipped for the same reason as `.claude/`.**
The generated export lands in the shared Agent Skills directory, so a workspace-local
install of it is `<workspace>/.agents/skills/billables-daily` — one level deeper than the
bare `skills/` shape, exactly like Claude Code's. Left unlisted, a Codex user's workspace
resolved to nothing while an identically-placed Claude Code install resolved fine, which is
the same silent-and-delayed failure this entry is about. The two names are now a set
(`HARNESS_DIRS`) rather than one hardcoded string, so the next harness is a name and not a
branch. Rung 2: the shape was read off the harnesses' own documentation and pinned in
`test_config_seam.py`; no user on one of them has been watched running the skill.

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

**This is one of two gaps with that symptom, and the narrower one.** The hook running is
not enough for the values to reach the script: the fragment is applied to Bash tool calls
alone, so on a machine that *has* Git Bash a command the model runs through PowerShell
finds nothing configured either. `winget install Git.Git` is the fix for this entry and
does nothing for that one. See § "Two ways the configuration does not arrive" — #28, which
also corrects the "every later shell command" claim this entry was written under.

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

### A day was read at one offset, so the day the clocks change came out wrong
**Rung 1.** 2026-08-31. Issue #8.

The zone arrived as a real zone in the entry above, but was immediately reduced to a single
number: `resolve_utc_offset` read the offset at local noon and both scripts applied it to
every instant in the day. Local noon is the right hour to ask about — midnight is where a
transition lands, and asking there is asking the ambiguous question — but the answer is
only good for a day that has one offset, and the transition day does not.

**What it cost, on `2026-04-05` in `Pacific/Auckland`.** That local day is twenty-five hours
long: it opens at UTC+13 and closes at UTC+12. Read at the noon offset it was asked for as
`[12:00Z, 12:00Z]` — an hour late at the start — so ActivityWatch was never asked for the
first hour of work, and what did come back was rendered an hour early. A session that began
at 00:40 reported beginning at 23:40 the previous evening. In spring the error runs the
other way: the twenty-three-hour day is asked for an hour early and pulls in an hour that
belonged to the day before. Nothing raises in either case; the day reads short and starts
in the wrong place, which is the same silent shape as the twelve-hour default it replaced.

**The fix is a type, not a calculation.** `resolve_zone()` hands the zone itself to the
arithmetic and every conversion goes through `to_utc()` / `local_clock()`, so each instant
is converted at the offset in force for *it*. `--utc-offset` resolves to a fixed-offset
zone, which is what passing a number has always meant, so that path is unchanged by
construction — and the six goldens that do not touch a transition regenerated
byte-identical, which is what says so.

**Two consequences, both pinned rather than papered over.** A span crossing the change is
reported at its *elapsed* length: 01:45–09:15 that morning is 510 minutes, an hour more
than the two clock times suggest, because the hour really passed and the AFK watcher really
recorded it. And the hour a fall-back repeats is genuinely ambiguous on the clock, so a
`--window` naming a time inside it gets the first pass over that hour — a convention, held
in one place (`to_utc`) so both scripts hold the same one. That second consequence was the
review's finding and became issue #17; the entry below settles it.

**Cost, accepted.** Headers name the zone (`zone Pacific/Auckland`) where they used to print
an offset, because on a transition day there is no single offset to print and printing one
would be a claim the run is not making. A `--utc-offset` run still reads `offset UTC+13`.

**What was not measured.** No real ActivityWatch instance was read across a real transition
— the transition day is a synthetic fixture, like every other scenario here, and what it
proves is that the arithmetic is zone-correct, not that AW's own event stream is.

### Two instants an hour apart printed the same clock time
**Rung 2.** 2026-08-31. Issue #17, raised by the review on #8 and carried here from
`## Open gaps`.

Rung 2 rather than 1 deliberately: no run was ever watched failing on a real fall-back day.
The reversal was reproduced in a test before it was fixed — a genuine assertion diff, not an
`AttributeError` — but that test was written from the review's reasoning, and every rung-1
entry in this file is a production observation. The grade is the weaker claim.

`local_clock()` rendered `HH:MM:SS` with no date, so on `2026-04-05` in `Pacific/Auckland`
the instants `13:30Z` and `14:30Z` — an hour apart, one either side of the change — both
printed `02:30:00`. The dateless clock is the established output shape and the reason an
overnight day ends at `01:12:00`, so #8 left it alone deliberately; but #8 is what made the
fall-back hour a supported case, and one string for two instants is not a rendering nicety
once someone bills from it.

**Three things it cost, all in one hour.** A break across the change rendered
`02:30:00-02:30:00` — sixty minutes shown as a zero-length string, and a range
`parse_range` would then refuse to read back as reversed. Two active spans an hour apart
abutted on the clock. And `activity_timeline.py` sorted its web rows *by the rendered
string*, so a tab opened at 02:40 on the first pass sorted after one opened at 02:10 on the
second, telling the model the day ran the other way round.

**Settled by marking the second pass, not by widening the clock.** `local_clock()` suffixes
it `*`; every other time on every other day is byte-identical, which is why the six goldens
that touch no transition regenerated unchanged. The marker is exact rather than decorative:
`parse_local_time()` reads it back into the returned time's `fold`, which `to_utc()` already
honoured, so a time lifted out of one script's output names the same instant when handed to
another's `--window` or `--cover`. Unmarked still means the first pass, so nothing written
before this changed meaning. The web-row sort moved to the instant.

**The scenario is the round-trip test.** `fall-back-repeated-hour-day` works either side of
the hour with an hour-long break inside it, and its `cover` and `windows` probes are written
in the notation the golden comes back in — `02:30*-04:15` covers 165.0 of 165.0 active
minutes, and `02:30-02:30*` is a 60-minute window at ratio 0.0 that was previously
unwritable, because both ends resolved to one instant.

**The DSL had to learn it first.** `Day.at()` localised with `fold=0`, so no fixture could
place an event in the second pass at all — the gap could not have been closed without also
closing it in the harness, which is why the marker is `support.second_pass()` as well.
`thin()` and `locked()` slice a range with `_fmt()`, which cannot carry the marker, so they
raise on one rather than silently generating every piece in the first pass.

**Cost, accepted — since closed in code.** The output shape is one character wider for one
hour a year. Anything parsing `HH:MM:SS` off these scripts has to tolerate it —
`harvest_post.py` does not, and `references/output-format.md` says to strip it there, along
with the older trap it sharpens: an entry spanning the change bills 2.75 hrs against 3.75
hrs really worked, because Harvest derives the duration from the two clock times.

That second half was accepted here as a prose mitigation and is no longer one. #23 made the
create refuse such an entry and name the two to post instead — see § "A create straddling
the fall-back was billed an hour short, silently". The judgement above still stands for what
it covered: the marker is a rendering decision, and whether the *write* path should refuse a
straddling entry was never the question in front of #17. What survives in
`output-format.md` is the case the refusal cannot see, where a block starts or ends inside
the repeated hour rather than containing it.

**A marker is refused where the clock reads once.** `09:00*`, and `03:00*` on that same
morning, raise rather than resolving quietly to the unmarked time — `zoneinfo` drops `fold`
on an unambiguous reading, so without the check the marker would mean something only
sometimes, with nothing in the output to say which case a reader was looking at. `03:00` is
the trap worth naming: it reads like the transition and is an hour after it. The instant the
clocks go back is `02:00*`, and no other clock string names it.

**Three things the review caught that a green suite did not.** All three were in the first
version of this change, and none would have failed a test:

1. **The `output-format.md` split example lost the hour it existed to save.** It told the
   model to split a straddling Harvest entry into `01:30–02:30` and `02:30*–04:15` — the
   fixture's own two blocks, where 2.75 hrs is the right answer *because there is a break
   between them*. For work run straight through, those two pieces omit 13:30Z–14:30Z and
   bill 2.75 against 3.75: the exact loss the bullet was written to prevent. The split has
   to be at the transition, and the two notations differ there — the scripts print
   `01:30 – 02:00*`, while Harvest must be posted `01:30`–`03:00` and `02:00`–`04:15`,
   because the transition instant reads 03:00 as you reach it and 02:00 once it has passed.
2. **The scenario shipped a golden with no named assertions**, against this file's own
   "a golden alone is not a test". Five now state the intent the golden only records.
3. **Two probes marked `03:00*`, which is a no-op** — and the `to_utc` refusal above exists
   because they were written that way without anything objecting.

**What was not measured.** Still no real ActivityWatch instance read across a real
transition, and no real Harvest entry posted on such a day — the `harvest_post.py`
consequence above is read off its argument handling, not observed. The split procedure in
`output-format.md` is arithmetic that has been checked twice, not a booking anyone has made.

### The confirmation gate is in the invocation, not only the prose
**Rung 3.** 2026-08-31, issue #9. `harvest_post.py` and `harvest_patch.py` write only when
passed `--confirm`. Without it they print the body they would have sent and exit 0.

**Why the gate is duplicated at all.** `SKILL.md`'s frontmatter carries
`disable-model-invocation: true`, which is what stops a model opening a billing run
unprompted. Claude Code honours it; several other Agent Skills harnesses drop it, and the
generated export for those harnesses is issue #11. Where the field is ignored, nothing but
the flag stands between a model that wandered into `scripts/` and a time entry on a
client-facing timesheet. So this is deliberate duplication of the kind
`changing-agent-instructions` calls load-bearing: the prose in Step 8 owns *when* the user
is asked, the flag owns *what happens if nobody was*.

**Five decisions worth not re-litigating.**

*A missing flag is a success, not an error.* Exit 1 would be the wrong answer twice over —
it tells a model reading stdout that the tool is broken, which is the whole reason the
`ERR` contract exists, and it throws away a preview that answers "what would this post?"
better than any error could.

*The preview prints the request body itself, not a rendering of it.* A preview that
describes the entry in its own words is a second description that can drift from the
first, and the user is then approving the paraphrase. `test_cli_contracts.py` runs the same
arguments twice — once bare, once with the flag — and asserts the previewed JSON equals the
body the confirmed run put on the wire, so the two cannot come apart.

*The existing guards run before the gate.* A reversed range is an `ERR` whether or not the
flag was passed. Previewing an unpostable command would invite a re-run with the flag, and
the guard would then fire on the second attempt with the user having read a preview of an
entry that was never postable.

*`--confirm` is not a field in `harvest_patch`.* Counted as one it would make
`harvest_patch.py <id> --confirm` an empty PATCH, which Harvest answers 200 to — the caller
told an edit landed when none was described. It is also exempt from the repeated-flag
guard: that guard exists because a repeated *value* flag silently last-wins.

*The documented command does not hand the flag over ready-typed.* Found by the review
subagent on the first draft, which put `--confirm` inline in Step 9's copy-paste template.
That makes writing the default action of the template, so a model that skipped Step 8 —
the case the flag exists to catch — posts anyway by pasting what the doc gave it. Step 9
now shows the command bare and the bullet under it says to append the flag once the yes is
in hand, which costs the correct path nothing: a model following the bullet still posts in
one invocation. `test_references.py` pins it, and distinguishes a bare `--confirm` on a
command from a `[--confirm]` in a list of a script's optional flags.

**One property found while writing the tests, and kept.** `harvest_patch.py <id> --notes
--confirm` sets the notes to the literal string `--confirm` and does **not** confirm, so it
previews. A value flag consuming whatever follows it is pre-existing behaviour, and this
gate fails closed under it.

**Overturned 2026-09-02, issue #9 — Rung 2.** The paragraph above is wrong about the harm,
and the review subagent that read the finished change is what caught it. "Fails closed" was
measured one invocation deep. The preview's own last line is `Re-run with --confirm to
apply it`, and a caller who does that reaches
`harvest_patch.py <id> --notes --confirm --confirm`, which the shipped parser answered
`('12345', {'notes': '--confirm'}, True)` — confirmed, with the flag written into a
client-facing timesheet as the note. The gate fails closed only until the user follows the
instruction the gate printed.

The two scripts had also drifted apart on where the flag may go, which no test measured.
`harvest_post.py` strips it from anywhere and its comment advertises "before or after the
positionals"; `harvest_patch.py` read the entry id off `argv[1]` before the loop, so
`harvest_patch.py --confirm <id> --notes 'x'` exited with `Unknown flag: <id>` — an error
naming the one argument that was correct. One documented gate, two grammars, and the
habit learned from the script the docs lead with is the one that fails.

`parse_args()` now removes `--confirm` before anything is read positionally, matching
`harvest_post.py`. `--notes --confirm` is `Missing value for --notes`, an honest usage
error; a leading `--confirm` works. Two tests in `test_cli_contracts.py` pin both.

*Why the original decision read as safe.* It was written from the parser outward — the flag
is consumed as a value, therefore it is not consumed as a flag, therefore nothing is
written. True of that one command, and the entry stopped there. What it never asked was
what the user does next, which the script itself had already told them.

**Consequence for the older suite.** Every invocation in `test_edge_harvest_api.py` now
carries the flag, refusals included. Without it the gate would block those runs on its own
and each guard test would pass whether or not the guard it names still existed.

**What was not measured.** No agent has been watched reaching these scripts unprompted on
a harness that drops the frontmatter field — that is the failure the flag is for, and it is
reasoned, not observed. Nothing has been posted to a real Harvest account through the flag
either. The evidence is the argument handling and the recorded request bodies, as
everywhere else in this file.

**One implementation, 2026-09-03, issue #22.** Everything above was true of two copies —
the strip, the reversed-time guard, the preview, the `OK` / `ERR` contract — one in each
write script, and the `--notes --confirm` fix was carried from one to the other by hand.
Both now declare their body to `scripts/harvest_write.py` (`create()` / `update()` →
`perform()`), which owns the gate and the two outcomes a write has. The preview and the
sent body are rendered from the same `Write`, so the drift the paired tests above guard
against is now impossible by construction, and `test_harvest_write.py` asserts it at the
function for both kinds of write without a script in between. Two rows left
`self-development.md` § "Rules with more than one copy" with this, as the ticket asked: the
gate rule has one copy in code. Its prose restatements — Step 8, Step 9, `README.md`,
`CONTEXT.md` — remain, and nothing holds them in agreement but reading; the review that
read this change said so, and the split of that table into instrument-held and reader-held
rows is #27's.

One message changed shape. `harvest_patch.py`'s reversed-range refusal used to say only
`--start (X) must be before --end (Y).`; it now carries the same explanation the create
gives — Harvest stores reversed times as 23h entries — because the guard is one function.
The reading script keeps its own two-line strip of `--by-day`: the gate is a property of
writing, and `harvest_list.py` does not write.

### Sharing a prefix is not proof of authorship — `install/export_agent_skills.py`
**Rung 2.** 2026-09-02. Issue #11, both findings raised by the review on the finished
change and reproduced against the shipped script before either was fixed.

Rung 2 rather than 1: no user has lost a skill to this. The two reproductions were run
from the reviews' reasoning, and every rung-1 entry here is a production observation.

The export retires directories that have left the plugin, and picked its candidates by
name — anything matching `billables-*` that this run had not just written. But the shared
Agent Skills directory is flat and the prefix is a namespace this plugin *claims*, not one
it owns: `~/.agents/skills/billables-mine` is a name a user is free to give a skill of
their own. Reproduced exactly that way, a hand-written skill with a `notes.md` beside it
was emptied, `rmdir`'d, and reported as `billables-mine (no longer part of this plugin —
removed)`. Nothing to undo it, and the line reads like housekeeping.

**The guard existed and was pointing the other way.** `refuse_unless_ours()` read "holds a
`SKILL.md`" as *this is a skill directory, so it is safe to overwrite*; retirement read the
same fact as *permission to delete*. One signal, two opposite meanings, and ADR-0004 stated
the stronger of the two ("cannot eat something it did not write") for both. Each export now
carries a stamp, and only a stamped directory is a retirement candidate. The distinction
that settles it: **overwriting** happens at a name this run chose anyway and takes the
weaker signal; **deleting** happens at a name the script did not choose, and takes proof.

**The second finding is the same guard failing closed.** Retiring a skill leaves the
directory holding nothing but the user's `.env` — deliberately; the credentials are not
ours to delete. `refuse_unless_ours()` then read that leftover as someone else's
directory, so a skill that left the plugin and came back — a rename undone, a trial
reversed — made *every* export from that machine exit `ERROR: … holds files this script did
not generate` until the user found and deleted a folder the script itself had left. The
error names a path, which is the only reason it would ever have been diagnosable.

**Why a green suite did not catch either.** The test asserting the blast radius
(`test_a_regenerated_export_leaves_alone_what_it_did_not_write`) used an *unprefixed*
fixture, `someone-elses` — a directory retirement was never going to look at. It stated the
claim it did not exercise, and it passed both before and after the defect. The three cases
now pinned in `tests/test_install_scripts.py` are the ones that vary: a foreign directory
inside the prefix survives, a stamped one that left the plugin is retired, and a retired
skill can be reinstated.

**What was not measured.** No user has been watched running the export over a shared
directory holding anyone else's skills — the collision is reasoned from the directory being
flat, which is what ADR-0004 says makes the prefix necessary in the first place. A
Windows case-only rename upstream is fixed in `prune()` by the same reading and is likewise
unobserved.

## Script defects

Found while building the scenario/contract suite, 2026-08-14. All **rung 1** — each was
watched failing before it was fixed, and each has a test that failed first.

### The suite was not hermetic, and one test wrote against production
`test_harvest_lookup.py` shelled out with `subprocess` to assert a non-zero exit on a
catalog miss. A subprocess inherits no fixture, so it read the real `.env` and fell
through to the live time-entries API, paging 180 days of real Harvest history — 4.7s of a
5.3s suite, and a red build whenever Harvest was slow. The same shape one flag over
(`harvest_post`) would have created a **real billable entry on a client's timesheet**.

Fixed by an autouse fixture that repoints both base addresses at an unroutable one and
blanks the credential sources, plus an in-process `run_cli`. The activity source is
redirected through its setting, `TIMESHEET_ACTIVITY_URL`, rather than by reassigning a
module global: `aw_client` used to freeze the resolved address into `AW_BASE` at import,
so overwriting that name was the only way to move it. The rule —
never `subprocess` a script from a test — is in `tests/README.md`, and `test_harness.py`
asserts the guard actually blocks, because a safety net nobody tests is one nobody knows
is there.

### Two scripts parsed the same `--window` flag differently
`afk_blocks` rejected `17:00-09:00`; `activity_timeline` accepted it and printed an empty
timeline, which reads as "nothing happened then" rather than "you typed it backwards".
Same class of defect the shared modules were created to end. `parse_range` moved into
`aw_client.py` and both called it; since #36 it lives in `timezone.py`, with the rest of the
zone arithmetic.

### `--json` did not always emit JSON
On a day with no `not-afk` activity, `afk_blocks --json` printed a sentence and exited 0.
Anything parsing the output fails on exactly the day it most needs a clean empty answer.
It now emits the normal key set with nulls; the text path keeps its sentence.

### Three CLIs crashed on import under captured stdout
`harvest_post`, `harvest_patch` and `harvest_list` called `sys.stdout.reconfigure()`
unguarded at import. Under pytest — or any harness swapping in a plain stream — that
raises `AttributeError`, which is why those three had no tests at all while
`activity_timeline` and `harvest_lookup`, which already guarded it, did. Guarded
identically. Superseded: the call is no longer made at import at all. The four scripts
that spawn children share `harvest_client.use_utf8()`, the other two reconfigure their own
streams, and every one of the six does it from `main()` — see "Configuration resolved at
import" below.

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

### One `fold` guard could not tell the two transition hours apart — rung 1, observed

Two defects, filed as #18 and #19, both reproduced directly before the fix. Neither came
from the change that surfaced them; both are from the repeated-hour work above, and both
were found by a review subagent reading the code rather than by anything in the suite.

**The shared cause is that `fold` was read as a boolean.** A wall clock changes offset in
two directions, and PEP 495 uses the same field for both: `fold=0` is always the offset in
force *before* a change and `fold=1` the one after. So a repeated hour shifts backwards
(`Pacific/Auckland`, +13 to +12) and a skipped hour forwards (+12 to +13). Asking only
whether the two offsets *differ* — which is what `to_utc` did — cannot separate them, and
neither can comparing two `datetime.time` objects, because `time.__eq__` and `__gt__`
ignore `fold` outright. The distinction needs the **sign** of the shift, and now lives in
one place, `clock_reads()`, which both callers route through.

**#19: the marker was accepted inside the hour the clocks skip, and read an hour early.**
`to_utc` refused a marker only where the two offsets matched. Inside a gap they differ, so
`02:30*` on `2026-09-27` sailed through and `zoneinfo` resolved it at the post-change
offset — `13:30Z`, local 01:30, an hour *earlier* than unmarked `02:30` at `14:30Z`. The
consequences were silent rather than loud: `--window 02:15*-02:45*` reported on 01:15–01:45
without saying so, and `--window 02:15*-02:45` returned ninety minutes from a thirty-minute
clock range. The docstring promising "a marker on a time that is not ambiguous is refused
rather than ignored" had been true for one of the two ways a time can fail to be ambiguous.

**#18: a one-ended marker on a fall-back day was reported as a spring-forward.** With the
instants running backwards, `parse_range` asked `hi > lo` on two `time` objects to decide
whether the clock readings were ordered. `fold` being ignored there, `02:30*` and `02:45`
compared as ordered, and the range took the clocks-skip branch: `'02:30*-02:45' spans the
hour the clocks skip on 2026-04-05` — a date on which nothing is skipped. The message sent
the reader hunting a transition six months away, which is the precise failure the comment
above that branch had been written to prevent. `02:00*-02:30` is the same shape and is what
a model writes after `output-format.md` tells it the split point is `02:00*`, so this was
reachable from the instructions rather than only from a typo.

The real cause there is the *end* of the range, not the range, and the message now says so:
mark both ends or neither. The skip branch is gated on a reading genuinely falling in a gap.

**The branch was tested, and the first draft of this entry said otherwise.** Review caught
it: `test_afk_blocks.py` has covered `02:00-03:00` on `2026-09-27` since 2026-08-31, and it
was green throughout, because on that input the branch fires correctly. The claim came from
grepping one test file rather than the suite — worth recording as a method note, since an
entry here that invents a blind spot sends the next person to fix a hole that is not there.
What was missing is narrower: no test asserted the branch fires *only* where a gap really
is, which is the half #18 broke. Both defects are now pinned in `test_timezone.py` under
"The hour the clocks skip" (`test_aw_client.py` until #36 moved the arithmetic), at the
shared module rather than through one script's re-export.

**What is refused and what is not, inside a skipped hour.** A marked reading and a spanning
range are refused by name. An *unmarked* reading is not: `02:30` on the spring morning still
resolves to `14:30Z`, the instant a clock left running would next have shown, which is the
standing convention `to_utc` documents and `utc_bounds` depends on for a zone whose change
lands at local midnight. So `--window 02:15-02:45` wholly inside the gap is accepted and
reports on 03:15–03:45. That was left alone deliberately — see `## Open gaps`.

### Configuration resolved at import, and an import that ended the process — #21

`refresh_catalogs` called `find_workspace()` at module scope and `fail_missing()` — a
`sys.exit` — when nothing answered. So `import refresh_catalogs` could end whatever was
importing: collection of any test file that named it, a caller reading `--help`, a tool
listing its flags. None of those wanted a workspace. `aw_client` froze the activity-source
address into `AW_BASE` the same way, and four scripts wrote `PYTHONIOENCODING` into the
process environment as they loaded.

The suite was paying for all three. Two test files carried a byte-identical `refresh`
fixture whose only job was to stage that import, under a paragraph headed IMPORT HAZARD.
`test_refresh_catalogs.py` had given up importing the module at all: it asserted against
the file's **source text**, including index arithmetic over the string to prove one
statement preceded another — so a rename failed it with behaviour unchanged, while a
behaviour change passed untouched. And the hermeticity fixture could only keep tests off a
real ActivityWatch by reaching in and reassigning `aw_client.AW_BASE`.

Settings now resolve where they are used. The fixture exists **zero** times rather than
once — with the hazard gone, `conftest`'s `workspace` fixture was already all those tests
needed. `test_config_seam.py` holds the rule for every bundled script, parametrized over
the directory rather than a list: nothing resolved, nothing written, no exit, on import.

Two things worth knowing about that guard. It spies on `skill_config.setting` and
`find_workspace` *before* the import, because `from skill_config import setting` binds at
import time. And it parks a sentinel value on every environment key a script assigns,
derived by walking the syntax tree — without that the environment half was green for the
wrong reason, since collection has already imported most of these modules and
`PYTHONIOENCODING` already held the value the write was about to set.

**Two observable changes, in a prefactor that claimed none.** `--dataverse-only` on a
machine with no resolvable workspace used to exit 1 with the workspace error, because that
error fired at import whatever the flags were; it now prints "Skipping Dataverse refresh"
and exits 0, since nothing it was asked to do needs a workspace. And on the default path
the workspace error now arrives *after* "Refreshing Harvest project assignments…" rather
than before any output at all.

**The hermeticity guard moved down a precedence layer.** It sets `TIMESHEET_ACTIVITY_URL`
rather than overwriting a module global, and `.env` outranks the process environment — so
a test that writes that key into the `env_file` or `workspace` fixture's `.env` would
defeat it and read the developer's real day. Nothing does, and `test_harness.py` only
proves the guard in its default state, so nothing would catch it. The hazard is written
into both fixture docstrings; that is the whole mitigation.

### The "Files in this skill" inventory had lost eleven flags — #26

**Rung 2.** 2026-09-02. The entry for `activity_timeline.py` stopped at `--gap-fold` and
named neither `--full` nor `--min-span`. `--min-span` is the one that mattered: it is the
tunable `references/context.md.example` maps a `## Preferences` line onto, so it was
documented in the template a user fills in and absent from the file a run actually reads.

Writing the comparison found nine more. `refresh_catalogs.py`'s entry named neither
`--harvest-only` nor `--dataverse-only`, and the shared `harvest_post` / `harvest_patch` /
`harvest_list` entry named `--confirm` and `--by-day` but none of `harvest_patch.py`'s seven
field flags — including `--hours`, whose module docstring calls it a footgun on start/end
accounts. A run reading only the inventory saw a patch script with a gate and no fields.
The inventory now carries the traps in a clause, not just the flag names.

**Flags are read out of the syntax tree, not out of a parser.** The first shape imagined
for this was "import every script, read its `argparse` parser" — which #21 had just made
possible. It does not reach: only four of the eleven scripts use argparse and all four build
the parser inside `main()`, so importing alone yields no parser, and the other three parse
by hand. The rule that covers all three shapes is textual — a string literal that is
*exactly* a flag is a flag the script compares an argument against — with one exclusion:
literals inside an argv list passed to `subprocess` belong to the other program.
`refresh_catalogs.py` hands `pac` four (`--name`, `--index`, `--environment`, `--xmlFile`),
and without the exclusion the inventory would have been told to list them. The regex is
deliberately case-tolerant so `--xmlFile` is excluded by the rule rather than missed by the
pattern. What this cannot see is a flag assembled at runtime; nothing here assembles one.

**Held per entry, not per script.** Three scripts share one line, so its flags are compared
against the union of what those three parse: a flag written there is known to belong to one
of them and not which. That is the price of the shared line, and it still catches both
directions of the drift this entry records.

**One copy is still unheld.** `skills/reconcile/SKILL.md` invokes `harvest_list.py --by-day`
and names `--window` and `--full`; it is a second skill's file and this gate reads only
`skills/daily/SKILL.md`. Renaming a flag now fails here and leaves that one instructing a
run to use — or in `--full`'s case avoid — a flag that no longer exists. Filed rather than
widened, so the scope of this entry is what it says it is.

**This reverses the "not fixed by a gate, deliberately" above.** That refusal was sound
about what it was refusing — a test asserting the list matches `ls` would have to encode
which files deserve a *description*, and the descriptions are the list's value. This test
holds no description. It holds two things a machine can check without judgement: every
shipped script has an entry, and each entry's flags match its scripts'. The prose stays
hand-written and ungated.

### A create straddling the fall-back was billed an hour short, silently — #23
**Rung 2.** 2026-09-02. Closes the consequence recorded as accepted in § "Two instants an
hour apart printed the same clock time", and #17's prose mitigation is reduced to what the
code does not cover.

Rung 2 rather than 1 for the same reason that entry is: the loss was reproduced before it
was fixed — `test_a_create_straddling_the_change_is_refused_rather_than_billed_short` was
written first and went red on the create reaching the fake Harvest with `01:30` and `04:15`
on it, which is the 2.75-hour body — but nobody has been watched under-billing a real
timesheet on a real transition day. The test in the tree is the one that now passes; its
red run is not something the repo evidences, only this sentence.

**The read side knew and the write side did not.** `local_clock` marks the second pass,
`to_utc` refuses a marker where the clock reads once, and `parse_range` names three separate
causes of a backwards range. `harvest_post.py` read no configuration at all: it took two
clock strings, checked that the second was larger, and posted. Harvest then derives the
duration from exactly those two strings, so an entry worked straight through the change is
short by the repeated hour — and it is well-formed, so nothing raises, and it reads
correctly in every listing afterwards. There is no later moment at which anyone finds out.

**The obvious rule refuses the two entries it recommends.** "The clock interval and the
elapsed time disagree" was the first design and it is wrong: `01:30`-`03:00` spans 1.5 clock
hours and 2.5 real ones, because a bare `03:00` on that date is the unambiguous reading an
hour after the change. Both replacements fail that test. What is actually unambiguous is
*containment* — an entry whose clock interval holds the whole repeated span cannot be right
on either reading — so that is what is refused, and an entry that merely starts or ends
inside the span is left alone because it bills correctly for one of its two passes. The
Phase-1 test asserts the two recommended entries post unchanged; it is the assertion the
first design would have failed, and it was written before the guard existed.

**The span is read, not assumed.** `transition_clocks()` bisects the day for the
change, because `zoneinfo` publishes no transition list and there is no supported way to ask
a zone when it next changes. Two zones are in the tests because each breaks an assumption
`Pacific/Auckland` cannot reach: `Australia/Lord_Howe` moves thirty minutes, so an assumed
hour would start the second entry half an hour too early and bill thirty minutes nobody
worked, and `America/Santiago` goes back *at
midnight*, reading `00:00` as it arrives and `23:00` once passed — the two readings in the
opposite order to New Zealand's. Direction therefore comes from the sign of the offset
shift, the same distinction `clock_reads` draws and for the same reason; reading it off the
order of the two readings gets Santiago exactly backwards. Its repeated span also wraps
midnight, which the containment test in minutes-since-midnight would otherwise read as
containing every entry of the day.

**It refuses rather than splitting**, per the ticket: two entries out of one approval would
put a body on the wire the user never previewed, which is the property the confirmation gate
exists to hold. The refusal fires before the preview as well, so nothing is offered that
cannot then be created — its own test, because every other refusal test passes `--confirm`
and the guard could move below the preview without one of them noticing.

**The boundary is strict on both ends, and that is a hole it cannot close.** An entry
*ending* at `03:00` or *starting* at `02:00` is accepted, because those are the two
entries the refusal itself recommends and it cannot refuse its own advice. But the same two
arguments describe a different morning: `01:30`-`03:00` where `03:00` is the unambiguous
reading an hour after the change is 2.5 hrs really worked and bills 1.5, and `02:00`-`04:15`
read as the *first* pass is 3.25 billing 2.25. Both are silent under-bills of exactly the
same shape as the one this closes, and no rule available to the script separates them —
the two intents are the same six characters. `references/output-format.md` carries them
alongside the start-or-end-inside cases, which is what "reduced to whatever the refusal does
not cover" amounts to: less prose than before, and not none.

**The gate from #26 earned its keep inside a week.** The zone message names `--utc-offset`,
which `harvest_post.py` does not have, so `resolve_zone` grew a way to omit it — written
first as a `offset_flag="--utc-offset"` parameter default.
`test_the_inventory_entry_lists_exactly_the_flags_its_scripts_parse` went red and wanted
`--utc-offset` added to the inventory entry of the module it lived in — `aw_client` then,
`timezone` since #36 — where it would have told every run that a module with no command
line takes an argument. A bare flag literal in a script is
indistinguishable from a flag that script parses, and the boolean the parameter became is
the simpler design anyway. Neither the test nor the reading that produced it was looking for
this.

**Cost, accepted.** Posting now requires `TIMESHEET_TIMEZONE` where it previously required
nothing — the standard `resolve_zone` message, minus the `--utc-offset` line this script
cannot honour, and an `### Upgrading` note. A plugin install has already supplied it; what
changes is running the one script on a machine configured for nothing else. `spent_date` is
also parsed now rather than passed through, so a malformed one is an `ERR` naming the format
instead of Harvest's own 422.

**What was not measured.** Still no real entry posted across a real transition. The hours in
the refusal are arithmetic checked against the read side's own fixtures, not a booking
anyone has made. Whether a model reading the message posts *both* entries rather than
"correcting" the overlap is untested — the message says not to, and that is a claim about
prose, which is what § "Three things the review caught" is a record of being wrong about.

**The update script, which this entry left open, closed by #32.** 2026-09-03. #23's Out of
scope named it and predicted it: the entry refused above can be *arrived at* by patching a
correct one, because Harvest recomputes the duration from the two clock times on a PATCH
exactly as it does on a create. `harvest_patch.py <id> --start 01:30 --end 04:15` left 2.75
hrs where 3.75 were worked, as silently as the create did.

The guard is on the *result*, not on the arguments, which is the whole of the difference. A
patch carries only what it changes, so `--start` alone, `--end` alone and `--date` alone are
each a complete straddling entry once laid over the one already on the server — and the
third is the one no reading of the arguments could reach, since it moves the date under
times nobody typed. That means a GET the script did not previously make, on the path where
PATCH semantics are already the documented trap. It is skipped where the answer is settled
without it: nothing time-shaped in the body, a `--date` naming a day with no repeated span,
or a body that already carries all three fields. Three tests assert the absence of that
request rather than the presence of the guard, because "does not pay for it" is the half a
passing refusal test cannot see.

**`--hours` is deliberately not refused, and the first version of that exception was a
hole.** The ticket's reasoning is that `--hours 3.75` states a duration the two clock times
cannot, so refusing it would leave a duration-mode account no way to correct the entry at
all. Written as `if "hours" in body: return`, that also let
`--start 01:30 --end 04:15 --hours 3.75` through — and Harvest recomputes hours from the
times whenever they are there, which this suite's own
`test_patch_sends_both_times_and_nothing_else_when_shifting_a_block` pins, so the entry
lands at 2.75 hrs with a `3.75` in the body that changed nothing. The exact entry the ticket
exists to prevent, reached by the command a model is most likely to assemble after reading
that `--hours` is allowed. The exception is now for `--hours` as the whole answer; found by
the review subagent, not by the suite, and the test that names it was written after.

**And the exception's premise does not hold on the usual account.** The module docstring
twelve lines above the guard says `--hours` on a start/end-time account — "most accounts,
including the typical consultancy setup" — leaves the entry inconsistent or converts it to a
running timer. So `--hours` is the right answer on a *duration-mode* account and not on the
common one, which is narrower than #32's wording. The behaviour stands as the ticket asked;
what changed is the prose, in `SKILL.md` Step 9 and `references/output-format.md`, which had
first been written to recommend it. The recommendation on a start/end-time account is the
create's own: patch the entry to the first of the two ranges and post the second.

**One message, imported rather than restated.** `harvest_patch.py` calls
`refusal_for_a_straddled_change()` — `harvest_post.py`'s at the time, `harvest_write.py`'s
since #36 — and prints what it returns, and the test
asserts *equality* with that function's output rather than a substring of it — the multi-copy
table registers one owner for this message, and a second wording would be a second thing to
keep true. What was extracted is `repeated_span()`, the cheap half of the question (is there
anything on this date to straddle?), because the patch asks it before deciding whether to
read the entry.

**Four costs, accepted, and one shape the guard cannot see.**

1. Patching a time or a date now requires `TIMESHEET_TIMEZONE` where it previously required
   nothing — same message, same `### Upgrading` note as the create's. A notes-only patch
   still asks for nothing, which is its own test.
2. **The read lands on the preview as well**, because a change that must not be applied must
   not be offered, which is the create's doctrine and the reason its guard runs before the
   gate. So previewing a time change now needs credentials, a reachable provider and an
   entry id that exists: a mistyped id answers `ERR 404` where it used to answer
   `WOULD PATCH`, and the workflow `SKILL.md` prescribes — preview, then confirm — costs two
   reads rather than the one the ticket priced. One per invocation is what the tests pin.
   Raised by review; the alternative (guard only the confirmed run) was rejected for putting
   a body in front of the user that the next command would refuse.
3. `--date` is parsed rather than passed through, so a malformed one is an `ERR` naming the
   format. It carries `harvest_post.py`'s consequence with it: `date.fromisoformat` widened
   on 3.11, so `--date 20260405` is now accepted and normalised where Harvest used to answer
   it with a 422 — on a verb that overwrites a line someone has already approved. Consistent
   with the create rather than novel, and noted here because the destructive verb is where
   it matters more.
4. `harvest_patch.py` imports `harvest_post.py` — a script — for the message and for
   `repeated_span()`. That is the multi-copy table's answer (one owner, imported not
   restated) and it is against the grain of `harvest_write.py`, which exists because shared
   write-path behaviour belongs in a module that is not an entry point. #36's `timezone.py`
   is where both functions should end up; ADR-0006's consequence bullet now records that the
   edge is two scripts wide. *Closed by #36:* `repeated_span()` is in `timezone.py` and the
   message in `harvest_write.py`, and no script imports a script — see § "Two provider
   scripts were importing the activity-source client".

And an entry whose stored times are absent (a duration-mode entry, whose `started_time` is
null) or unreadable is left alone: there is no clock interval to straddle, and inventing one
would block the accounts `--hours` exists for. A deliberate hole in the same family as the
strict boundary above — the guard refuses what it can measure.

**What was not measured**, on top of the create's own gap: no real entry has been patched
across a real transition either, and the GET's response shape is the fake's (`spent_date`,
`started_time`, `ended_time` as Harvest documents them), not one observed from the API. Nor
is it observed that Harvest ignores a `hours` field sent alongside times — the guard above
is written as though it does, which is what this suite's own patch tests assume and what the
module docstring has said since before them.

### Two ways the configuration does not arrive, and only one had a name — #28
**Rung 1.** 2026-09-02. Issue #28.

A fresh install with `/plugin configure billables` fully filled in, and the first
`/billables:daily` says the Harvest credentials are not found. Starting a new session does
not help, because the session is not what is broken: the values arrive for the **Bash**
tool and for nothing else, and the script the model reached for happened to be run through
PowerShell.

**The bridge works. Its scope is narrower than the repo said it was.** The SessionStart
hook writes `export KEY='…'` into `$CLAUDE_ENV_FILE`, and Claude Code applies that file as
a preamble to Bash tool calls. The PowerShell tool is given no equivalent — and loads no
profile either — so the fragment reaches it in no form at all. One docstring said the
fragment applies to "every later shell command" outright
(`hooks/publish_plugin_config.sh`); three more described the round trip without ever
stating a scope (`hooks/publish_plugin_config.py`, `tests/test_plugin_config.py`,
`scripts/skill_config.py`), which is what let a reader supply the wide reading. All four
now say Bash.

**Measured, not read off the documentation.** A throwaway project with one SessionStart
hook that appends a probe variable to `$CLAUDE_ENV_FILE`, then a single headless run
asking for the variable from each tool:

```
bash: PROBE_BRIDGED=yes
pwsh: PROBE_BRIDGED=UNSET
```

The hook itself recorded that it ran and which file it wrote, so "the hook did not fire"
is excluded rather than assumed. The harness documents the two halves that make this
predictable — the env file is applied "before each Bash command", and PowerShell profiles
are not loaded — but *not* the negative, that the PowerShell tool has no equivalent. That
came from the probe.

**This is not the limitation already recorded**, and conflating them costs the user an
install. The older one — the hook needing a POSIX shell — is a machine with no Git Bash,
where the hook never starts and nothing is published to any shell; its fix is
`winget install Git.Git`. Here Git Bash is present, the hook ran, and the fragment is
correct. `winget install Git.Git` does nothing for it.

**The first diagnosis was wrong, and the review is what caught it.** It asked whether Git
Bash's `MSYSTEM` was set, as a proxy for "did this command come from the Bash tool" —
verified in both tools and in a `python -c` child of each, which is the process that
prints the message. The proxy does not hold: **`MSYSTEM` is inherited from whatever
launched Claude Code, not set by the tool.** Start the session from a Git Bash terminal
and the PowerShell tool carries it too, so the note fell silent for exactly the population
it was written for — a population the plugin selects, since the publishing hook is
`sh "…publish_plugin_config.sh"` and Git Bash is therefore a precondition. Reproduced by
running a nested session from the Bash tool and reading the function's own output in the
PowerShell tool: `MSYSTEM='MINGW64'`, note empty. A user with MSYS2 on their machine was
silenced in both tools.

Worse than the bug: the tests could not see it. The four cells were driven by argument,
and the "Bash tool" cell was spelled `{"CLAUDECODE": "1", "MSYSTEM": "MINGW64"}` — which
is *also* the PowerShell tool under inheritance. The test asserting silence there passed
while naming a behaviour that was broken. A test built on the same false premise as the
code is worth less than no test, because it reports the premise as verified.

**What replaced it is the fact rather than a proxy for it.** The publishing hook now
exports one marker that is not a declared setting, `BILLABLES_CONFIG_PUBLISHED`, in the
same fragment as the values. A process either received that fragment or did not; nothing
about shells, launchers or inherited environments can deliver the values without the
marker, because they are one write applied as one preamble. The marker is written even
when nothing is configured — the unconfigured user is precisely who reads a missing-setting
message, and withholding it there would merge "you have not configured this" with "your
configuration did not arrive", which is the one distinction it exists to draw.

Verified end to end against the shipped publisher, not only in the unit tests: the same
throwaway project, with `hooks/publish_plugin_config.py` itself as the SessionStart hook
and nothing configured, so the marker is the only thing it writes.

```
bash: MARK=1
pwsh: MARK=ABSENT
```

Two costs, both taken deliberately. The spelling now exists twice, because a hook is run
by path and can import nothing from the skill;
`test_the_marker_the_scripts_look_for_is_the_one_the_hook_writes` pins them, and a
mismatch on either side would have failed nothing while making every session look
unpublished. And the note can no longer say *which* of the two causes it is — the fragment
is equally absent when the hook never started — so it names both and says plainly that a
new session will not help, which is the line it is displacing.

**It speaks only for a plugin install.** An exported or hand-installed copy reads its
values from `.env` and has no publishing step at all, so the marker is permanently absent
for it; without a gate the note would fire on every missing setting there and recommend
two things that change nothing. A hand-installed copy under `~/.claude/skills/` is loaded
inside a session like any other, so the session check alone does not cover it. The gate is
`_is_a_plugin_install()`, extracted from the `.claude-plugin/` check `_install_workspace()`
already made for the opposite reason.

**`sh --version` was the wrong discriminator and is gone.** `references/setup.md` used it
to separate the two causes. A default Git for Windows puts only `Git\cmd` on `PATH` while
`sh.exe` lives in `Git\bin`, and Claude Code resolves its shell without `PATH` — so it
fails on a machine whose Bash tool works perfectly, routing a cause-1 user to cause 3's
fix, which is the misroute this ticket exists to remove. Measured in the PowerShell tool
on a machine with a working Git Bash and a working Bash tool: `Get-Command sh` returns
nothing. What separates the causes is something the model already has and no probe can
improve on: re-run the failing command through the Bash tool.

**Three sites, not one, and the rule is about reads.** `daily/SKILL.md` said to read
`TIMESHEET_SCREENSHOTS_DIR` and then listed the folder in PowerShell; `reconcile/SKILL.md`
did the same, where an empty read makes a healthy month look like a month nobody worked;
`setup/SKILL.md` told the model to pass the configured value to a `.ps1` it necessarily
runs through PowerShell, where an empty read registers the capture task against the
default and points the writer and the reader at different folders. A "run the scripts
through Bash" rule would have left all three.

**And the obvious way to read it in Bash is also wrong.** `echo "$TIMESHEET_SCREENSHOTS_DIR"`
reads the process environment, which is one of four layers and not the one an exported
install keeps that value in — so it returns empty for a user whose capture task is writing
somewhere else entirely, and the listing falls back to the default folder: the same
divergence, produced by the fix. The three sites now call
`screenshot_capture.py --where`, which resolves through the seam and expands a `~`. That
last part closed a live hazard of its own: `resolve_screenshots_dir()` did not
`expanduser`, so a `~/Pictures/Shots` in a `.env` made the capture write to a directory
*named* `~` under the task's working directory.

**The suite's own verdict had to be pinned, and the pin needed a test that could see it.**
A conditional tail on a message is invisible to every substring assertion in front of it —
the same blind spot #23 closed by pinning a message whole — so `conftest` deleting the
session marker looked load-bearing and was not: removing it left the suite green in both
shells. The credentials test now asserts where the message *stops*. With that in place,
removing the pin and running through the PowerShell tool fails it by name, and running
through Bash does not, which is the two-shell difference the pin exists to remove.

**Three mechanisms that would have closed it properly, all rejected.**

- *Read the fragment the hook already wrote.* Both tools receive `CLAUDE_CODE_SESSION_ID`,
  and the file sits at `~/.claude/session-env/<that id>/sessionstart-hook-0.sh` — verified:
  this session's directory exists under its own id, and the probe's held exactly the 25
  bytes its hook wrote. It costs no new file and no new on-disk exposure. Rejected for
  depending on an undocumented path: when the layout changes the fallback stops working
  silently, which is a safe direction — back to the behaviour above — but not one any test
  in this repo could catch.
- *Write the values to `$CLAUDE_PLUGIN_DATA`*, which is documented, survives updates, and
  is readable from either shell. Rejected because it puts a second plaintext copy of the
  user's token on disk, and "there is no secrets file for this skill to create, read or
  share" is a claim `SKILL.md` makes to the user and `tests/test_plugin_config.py` holds.
- *Let the scripts read the harness's own storage* — the ticket's third fix candidate.
  `settings.json`'s `env` block does reach **both** tools (measured), which is what makes
  this look available; but a plugin cannot write it. A hook would have to edit the user's
  own settings file, and the credentials are declared sensitive precisely so they stay out
  of it — writing them there is the `$CLAUDE_PLUGIN_DATA` objection with a worse filename.
  Reading `pluginConfigs` instead covers only the non-sensitive half: the credentials live
  in the harness's credential store, whose programmatic shape is documented nowhere and is
  an OS keychain on macOS.

None is closed off. The evidence is here so a reopening starts from the facts rather than
re-deriving them.

**Cost, accepted, and stated plainly.** The ticket's first two acceptance criteria are not
met as written. A script the model invokes through PowerShell still does not resolve its
settings, and the repro stays red by design — it measures the harness, and the harness has
not changed. What changed is that every path the skills direct now reads in Bash, and the
one failure left says which shell to re-run in. Recording that as "fixed" without saying so
would be one more claim about this bridge that is wider than the bridge.

**What was not measured.** No run was watched hitting the note and re-running itself in
the other shell; that a model does the obvious thing with "re-run this same command
through the Bash tool" is a claim about prose, and the first version of this entry made a
claim about a shell marker that turned out to be false. The marker is only as good as the
hook that writes it — a session where the hook fails after opening the env file would
publish neither, which reads as "did not arrive" and is true. And the note is suppressed
outside a session, so a bundled script run by hand from a terminal never sees it, which is
right today and would be wrong if that route ever gained a published layer.

### Two provider scripts were importing the activity-source client — #36
**Rung 3.** 2026-09-03. No observed failure: nothing was wrong with the arithmetic, and the
suite was green before and after. What was wrong was the direction of an import.

`harvest_post.py` and `harvest_patch.py` both imported `aw_client` — for `resolve_zone()`,
`zone_label()` and `transition_clocks()` — so the provider adapter reached into the activity
source to date the day it was billing. ADR-0006 says an adapter that does that is not behind
a boundary, and #33 moves the boundary, so the edge had to go first or travel with it. #32
had widened it: a second provider script, and a second edge beside it, `harvest_patch.py`
importing `harvest_post.py` — a script — for the refusal message and for `repeated_span()`.

**What moved.** `scripts/timezone.py` now holds every function that answers a question about
a zone or a clock reading: `resolve_zone()`, `zone_label()`, `parse_local_time()`,
`clock_reads()`, `to_utc()`, `transition_clocks()`, `repeated_span()`, `parse_range()`,
`utc_bounds()`, `local_clock()` and the marker they share. `aw_client.py` keeps what it was
named for — bucket discovery, the request, the heartbeat collapse, and the server's address.
Not one line of the arithmetic changed, and no assertion about it changed either; the
daylight-saving tests moved from `test_aw_client.py` to `test_timezone.py` as they stood.

**The refusal message did not go with it, and the ticket said it should.** #36's comment
asked for `refusal_for_a_straddled_change()` in `timezone.py` alongside `repeated_span()`.
It is in `harvest_write.py` instead, for the reason the comment itself gives: the convention
being broken is that one — "not a script … everything a write has in common happens here,
once" — and this is a guard shared by the two writers, the same shape as `ordered_minutes()`
already there. The split is where the two halves of the question fall. *What the clocks did
on a date* is the zone's, and a second provider adapter would ask it unchanged; *that
Harvest bills the difference between two clock times, so post these two entries instead* is
the provider's behaviour and its wording, and a second adapter would need its own. Put in
`timezone.py`, that paragraph of Harvest prose would sit in the module both day-reading
scripts import beside the activity-source client — reintroducing, as vocabulary, the
coupling the ticket removed as an import. (`aw_client.py` itself imports nothing of it:
what was left there after the move needs no zone at all.)

**The instrument is new, and it is the acceptance criterion.** `tests/test_module_boundaries.py`
reads each script's imports out of its syntax tree and holds three rules: no `harvest_*.py`
imports `aw_client`, nothing imports a module with a `__main__` guard, and `timezone.py`
imports neither half. Both populations come from `scripts/`, so a new script is held the day
it lands. It was written first and failed on five counts against the tree as it stood, which
is what said the two edges were exactly where ADR-0006 claimed. That red run is not a
rung-2 measurement smuggled in: an import edge is visible in the source and needed no
measuring. What it bought was the instrument, and the knowledge that the instrument can
fail — a boundary test that has never been red is a test of nothing.

**A fourth check, on the other direction.** Every module that *calls* `resolve_zone()` must
import the module that defines it — read as identifiers rather than as text, because
`harvest_client.py` names the function in prose to say which absence it shares its wording
with, and a text search cannot tell a cross-reference from a call. Without it, "no provider
script imports `aw_client`" is satisfied just as well by a script growing its own copy of
the resolution, which is the duplication the shared module exists to prevent.

**What was not measured.** Nothing about behaviour, deliberately — the claim is that this
change has none, and the evidence is the whole suite green with the goldens untouched —
861 collected, 856 passing and the five benchmarks skipped as they are by default — and
`pyright` at zero. The module name is the one risk taken: `scripts/` is on `sys.path` at run time, so
`timezone.py` shadows any third-party top-level module of that name for these scripts. There
is no such module in the standard library (`datetime.timezone` is an attribute and
`zoneinfo` is the package), and the scripts have no third-party dependencies at all, so the
exposure is a future dependency named exactly `timezone` — checked by hand, not by a test.

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
it in the product (since #24 that line is in `day_skeleton()`; the lesson is unchanged). Reverting that single line — gap detection built, tested, and wired to
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

### An unmarked `--window` *starting* inside the hour the clocks skip is accepted — undecided

Left as-is while fixing #18/#19, 2026-09-02, and recorded because the reasoning is finely
balanced rather than settled. An unmarked reading inside the gap resolves forward to the new
offset, so any range starting there has its start moved an hour later than written — the
same plausible-wrong-answer shape both those defects were about.

The accepted set is wider than "wholly inside", which is how this entry was first written,
and the governing quantity is not the length of the range — a second draft said that too,
and the table is here because both readings were wrong. What decides it is whether the
*other* end is also in the gap. Measured on `2026-09-27` in `Pacific/Auckland`:

| `--window` | Clock | Real | Result |
|---|---|---|---|
| `02:15-02:45` | 30m | 30.0m | accepted, reported on 03:15–03:45 |
| `02:05-02:55` | 50m | 50.0m | accepted, reported on 03:05–03:55 |
| `02:45-03:00` | 15m | — | refused as spanning |
| `02:00-03:00` | 60m | — | refused as spanning |
| `02:30-03:30` | 60m | — | refused as spanning |
| `02:30-03:45` | 75m | **15.0m** | accepted, an hour short |
| `02:30-04:00` | 90m | **30.0m** | accepted, an hour short |

Both ends inside the gap resolve at the same pre-change offset, so the range keeps its
length and moves wholesale to the hour after. Only the start inside, and the end keeps its
own offset while the start is relabelled, so the range loses exactly an hour — refused when
that leaves nothing, accepted silently short when it does not. The refusal is therefore a
side effect of the arithmetic collapsing rather than a check anyone wrote, and a 15-minute
range is caught while a 90-minute one is not. The long ones are the dangerous shape, because
a shortened `window_min` also shrinks the denominator `active_ratio` is measured against.

Two things argue for leaving it. `to_utc` documents the forward-resolution convention
explicitly and `utc_bounds` calls the same function for both ends of a day, so refusing an
unmarked gap reading *there* would break a zone whose change lands at local midnight, and
neither issue asked for it. Refusing it in `parse_range` alone would be safe and narrow, and
is the change to make if this is picked up — the two functions would then disagree about the
same reading, which needs a sentence in the `to_utc` docstring saying why.

`references/activitywatch.md` states the current behaviour outright rather than implying a
refusal; the line before this change promised one, which is what makes this worth an entry
instead of a silent decision.

### An entry across a spring-forward is over-billed and not refused — out of scope on #23

2026-09-02, and the mirror of the fall-back refusal that shipped with it. On the morning the
clocks go forward, `01:30`-`04:15` in `Pacific/Auckland` is 1.75 hrs of real time and Harvest
bills the 2.75 the two clock strings say — over-billing a client rather than under-billing
them, which is the worse direction to be silent in.

`transition_clocks` finds the day and reports which way it went, so the guard *could* fire
here; it deliberately does not, and the tests say so by name. Two reasons, and neither is
"harder". The pieces degenerate: `01:30`-`02:00` and `03:00`-`04:15` are separated by a gap
where the fall-back pair abut, and either end of the entry can land inside the skipped hour
and leave one piece empty. And the message would be the fall-back one inverted — an
apparent *gap* that must not be closed rather than an apparent overlap — so showing one
wording for both is the failure § "One `fold` guard could not tell the two transition hours
apart" already records: naming the wrong transition sends a reader hunting one six months
away, which is worse than naming none.

#23 scoped it out and this is where it waits. The entry above on the unmarked `--window`
into the skipped hour is the read-side half of the same hour.

**#32 gave it a second instance, on the write path it did not have before.** The patch
guard declines a spring-forward for the same reason and by the same route — it asks
`repeated_span()`, which answers None there — so a patch can now *arrive* at an over-billed
entry as well as a create. Nothing new to decide: whatever closes this closes both, because
both ask one function. Named here so the gap is not read as a create-only one.

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
