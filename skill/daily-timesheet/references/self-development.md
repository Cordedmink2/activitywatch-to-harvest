# Changing this skill

Read this before editing `SKILL.md`, anything in `references/`, or the scripts. It is
not needed to run a timesheet — skip it on a normal run.

The general method lives in the `changing-agent-instructions` skill: reproduce, watch a
fresh agent do it unprompted, baseline against an instrument that fails when the
knowledge is lost, one change at a time, re-check the baseline afterwards. What follows
is what is specific to *this* skill.

## Where maintenance content goes

| Content | Home |
|---|---|
| What to do on a run | `SKILL.md` / `references/` |
| One user's clients, signals, machine facts | that user's `Timesheets/.context.md` |
| How to change the skill — this file's subject | this file |
| Test records, settled decisions, rejected options, evidence rungs | `TESTING.md` |
| Releasing and propagating a change | the `daily-timesheet-release` skill |

`SKILL.md`'s "What lives where" section governs the first two rows at *run* time — it is
what Step 11 sorts proposals against. This table is the maintainer's view of the same
split, extended to the files a run never touches.

**New findings go in `TESTING.md`, not `SKILL.md`.** It carries the evidence rungs (1
observed failure / 2 observed hazard / 3 reasoned) that its entries are graded against,
and the record of what was already measured and rejected — read it before re-adding
something a test found unnecessary.

## The instrument

`tests/` measures the *scripts*. It stays green while the instructions break, so it is
not the instrument for a wording change — `TESTING.md` § "What the instruments measure"
has the full argument and the fixture design that has been used so far.

Two gates a doc edit can trip, both cheap to run from the skill folder:

- `python -m pytest -q` — `test_references.py` scans `SKILL.md` and every
  `references/*.md` (globbed, so a new reference file is covered automatically) and
  fails any `python scripts/<name>.py` command naming a script the skill does not ship.
  Write workspace-relative commands some other way.
- A `.context.md` under the Step 11 size budget after any change that proposes writing
  to one.

## Rules with more than one copy

Duplication here is mostly deliberate — a guard restated in the pre-post checklist
catches what a guard buried in Step 6 does not. The hazard is scope drift: each copy
reads fine alone and the contradiction exists only across them. Before changing any of
these, change every copy, and search for the *rule* rather than the wording you happen
to have in front of you.

| Rule | Owner (carries the reasoning) | Restated at |
|---|---|---|
| `--cover` takes every entry Step 9 will post | Step 6 guard 3 | Step 8 checklist |
| `work_end` is a ceiling | Step 3, second bullet | Step 6 guard 2, Step 8 checklist |
| No entry under 0.25 hr | Step 3, `0.4–0.7` band | Step 3 granularity line, Step 6 guard 1 |
| Per-user facts belong in `.context.md` | "What lives where" | Step 11, Non-negotiables |
| Task selection and interleaved days | `references/classification-rules.md` | Step 4 points at it |
| One date per session | Step 12 | Step 1 scope paragraph, Step 10 wrap-up |
| Read `.context.md` whole, never partially | Prerequisite 1 | Step 2 load list, Step 11 size budget |
| Check the date against Harvest before rebuilding it | Step 1 | Step 8 checklist |
| Timesheet-admin time needs a screenshot before it is booked *or* accepted | `classification-rules.md` billing conventions | Step 1 already-covered branch |

The `--cover` pair has already drifted once and cost a re-run — `TESTING.md` has the
entry. The fix at the time touched the checklist copy and missed the owner.

Don't write exclusivity claims ("this is the only place that says X") into any of these
files. They enforce a snapshot and rot silently into something that still reads as
authoritative.

## Releasing

The skill exists in three copies and a change is only done when all three agree. The
`daily-timesheet-release` skill owns that ritual — VERSION, `CHANGELOG.md`, tags, which
direction to propagate, and how to verify each leg. Don't bump `VERSION` by hand here.
