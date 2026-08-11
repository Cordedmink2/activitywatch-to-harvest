# Testing & Improvement Record

Not part of the operating instructions. `SKILL.md` says what to do; this file holds
why it says it — test records, settled decisions with their evidence, and the options
that were considered and rejected. Read this before changing `SKILL.md`; skip it if
you are just running a timesheet.

Method: `changing-agent-instructions`. The rule that governs this file is **never
encode a diagnosis you have not watched happen**.

## What the instruments measure

`tests/` measures the *scripts*. It stays green when the instructions break, so it is
not the instrument for a `SKILL.md` change — it only guards against a doc edit that
invalidates a script path or command shape (`test_references.py`).

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

## Rejected

- **A Step 3 pointer to the lock-screen quirk.** Measured 6/6 against a control arm — see
  the entry directly above. The reference index line already routes it.
- **A rule about `harvest_list.py` argument shape.** The flags `--from/--to` were
  guessed and failed; the script takes positional dates. But `SKILL.md` already
  documents the positional form in two places. The doc was right and went unread —
  adding a third statement rewards not reading, and grows the doc for nothing. What the
  agent already gets right from existing text needs no rule.
- **Global `python` → `py`.** See above.

## Open gaps

- **REOPENED: does anything route an agent to `activitywatch.md` when the anomaly is not
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
- **Every result in this file comes from one fixture** (a fictional two-client day with three
  lock-shaped stretches). It exercises breaks/idle/attribution and nothing else. Backfill,
  meetings, support tickets, and single-client days are unmeasured.
- The earlier three `SKILL.md` changes (interpreter, capture-health, skeleton freshness)
  remain unvalidated against a control.
- The Step 8 skeleton-freshness line is rung 2 and may be unnecessary; it has a
  deletion condition written into its entry.
- `tests/` has no coverage asserting `SKILL.md`'s *behavioural* claims, and by the
  method above it never usefully will — don't add doc-behaviour assertions there.
