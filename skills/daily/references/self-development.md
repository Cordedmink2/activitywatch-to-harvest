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
| The vocabulary a rule is written in, and which words to avoid | the repo root's `CONTEXT.md` |
| Why the code is shaped the way it is | the repo root's `docs/adr/` |
| Releasing a change | `.claude-plugin/plugin.json` `version` + `CHANGELOG.md`, then a tag — see §Releasing |

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

Three gates a doc edit can trip. **Run them from the repo root, not the skill folder** —
`pytest.ini` here sets `testpaths = tests`, so a run started in this folder collects the
skill's own suite and silently skips every repo-level guard:

```
python -m pytest -q tests skills/daily/tests
```

- `skills/daily/tests/test_references.py` scans `SKILL.md` and every `references/*.md`
  (globbed, so a new reference file is covered automatically) and fails any
  `python scripts/<name>.py` command naming a script the skill does not ship. Write
  workspace-relative commands some other way.
- `tests/test_provider_neutrality.py` fails if a provider's literal task name returns to
  the shipped rules, if the rules name a work kind the glossary doesn't define, or if the
  work kinds in `references/context.md.example` drift from the ones in `CONTEXT.md` — that
  last pair is matched string-for-string at run time.
- A `.context.md` under the Step 11 size budget after any change that proposes writing
  to one.

A code edit has a second gate, also run from the repo root:

```
pyright
```

`pyrightconfig.json` there is what makes it — and an editor's language server — read *this*
repo. Pyright walks up from the working directory looking for that file, so a checkout
nested inside another project inherits that project's root and type-checks the neighbouring
tree instead: the file is worth keeping even if every setting in it were a default, because
drawing the boundary is most of its job. It also pins `pythonVersion` to the 3.10 floor
`README.md` §Prerequisites states, so a stdlib or syntax feature added later fails here
rather than on a user's machine, and it declares the `sys.path` entries
`skills/daily/tests/conftest.py` adds at run time, which pyright does not execute.

The gate is zero errors. Reach it by fixing what is reported — a rule turned off to get
back to green takes the rest of its file's coverage with it.

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
| Work kind and task selection, and interleaved days | `references/classification-rules.md` | Step 4 points at it |
| The rules name a work kind; the user's workspace names the provider's task. No task name is a shipped default | the repo root's `CONTEXT.md` glossary, and `docs/adr/0002-defer-splitting-the-provider-into-its-own-plugin.md` for why | `references/classification-rules.md` §"Work kind and task selection", `references/context.md.example` §"Work kinds", `SKILL.md` "Tunable defaults" + Step 4, the repo-level `tests/test_provider_neutrality.py` |
| One date per session | Step 12 | Step 1 scope paragraph, Step 10 wrap-up |
| Read `.context.md` whole, never partially | Prerequisite 1 | Step 2 load list, Step 11 size budget |
| Check the date against Harvest before rebuilding it | Step 1 | Step 8 checklist |
| Timesheet-admin time needs a screenshot before it is booked *or* accepted | `classification-rules.md` billing conventions | Step 1 already-covered branch |
| A skill defect goes upstream, not into `.context.md` | `references/reporting-issues.md` | Step 11 third bullet |
| Screenshots never settle active/idle | Step 5, first bullet | `SKILL.md` folder mechanics, `classification-rules.md` §"Focused window ≠ active attention" |
| Check the other monitors before trusting one | `classification-rules.md` §"Focused window ≠ active attention" | `SKILL.md` folder mechanics + Step 5 subagent brief, `classification-rules.md` long-agent-CLI and browser-row paragraphs, interleaved-days probe step |
| Setting precedence: flag, then `.env`, then the process environment, then the script default; blank counts as unset | `scripts/skill_config.py` docstring | `SKILL.md` "What lives where", `references/setup.md` §"First-run: configuration", the `refresh_catalogs.py` and `screenshot_capture.py` module docstrings |
| The declared configuration surface: which keys exist, which are required, which are sensitive | `.claude-plugin/plugin.json` `userConfig` | `tests/test_plugin_config.py`, `references/setup.md` §"First-run: configuration" table, `README.md`'s install table |
| The Python the scripts must run on: 3.10 | `README.md` §Prerequisites | `pyrightconfig.json` `pythonVersion`, which is what enforces it |
| No assumed timezone: an unconfigured run refuses rather than guessing an offset | `scripts/aw_client.py` `resolve_zone()` docstring | `SKILL.md` "Timezone", `references/activitywatch.md` §"Time zones", both scripts' module docstrings |
| A day is bounded by its zone at each end, not by one offset — so the day the clocks change is 23 or 25 hours long | `scripts/aw_client.py` `utc_bounds()` docstring | `references/activitywatch.md` §"Time zones", `SKILL.md` "Timezone", `tests/scenarios.py` `daylight-saving-transition-day` |
| The second pass over the hour a fall-back repeats is suffixed `*`, and reads back as the same instant | `scripts/aw_client.py` — `local_clock()` writes the marker, `parse_local_time()` / `to_utc()` read it back and refuse it wherever the clock does not read twice | `references/activitywatch.md` §"Time zones", `references/output-format.md` §Conventions, `SKILL.md` "Timezone", `tests/README.md` §"Dating a day", `tests/scenarios.py` `fall-back-repeated-hour-day`, `TESTING.md` §"Two instants an hour apart printed the same clock time", `CHANGELOG.md` |
| The two transition hours are told apart by the *sign* of the offset shift across `fold`, never by the fact that there is one — a repeated hour shifts back, a skipped one forward | `scripts/aw_client.py` `clock_reads()` docstring | `to_utc()` and `parse_range()`, which both route through it, `references/activitywatch.md` §"Time zones" last two bullets, `TESTING.md` §"One `fold` guard could not tell the two transition hours apart" |
| The shared-directory export is prefixed `<plugin>-<skill>`, its declared `name:` rewritten to match, and it is generated rather than hand-edited | `docs/adr/0004-generate-the-shared-agent-skills-export.md` | `install/export_agent_skills.py` module docstring, the repo-level `tests/test_distribution.py`, `README.md` step 5 |
| The export deletes only what carries its stamp — the prefix says where to look, never who wrote it | `TESTING.md` §"Sharing a prefix is not proof of authorship" | `install/export_agent_skills.py` `retire_departed_skills()` / `refuse_unless_ours()` docstrings, `docs/adr/0004-…` §Consequences, the three retirement tests in the repo-level `tests/test_install_scripts.py` |
| Writing to the provider takes `--confirm`; without it the scripts preview the exact body and exit 0, so a forgotten flag is a preview and not an error | `TESTING.md` §"The confirmation gate is in the invocation, not only the prose" | both write scripts' module docstrings, `SKILL.md` Step 8 + Step 9 + the patch line + Non-negotiables + "Files in this skill", `README.md`, the repo root's `CONTEXT.md` glossary, `tests/test_references.py`'s ready-typed-flag guard, `tests/test_cli_contracts.py` |
| The gate is removed from the argument list before anything is read positionally, so it may be typed anywhere and no dangling field flag can swallow it | both write scripts' `--confirm` handling — `harvest_post.py` is where the shape was set | `harvest_patch.py` `parse_args()`, the two placement tests in `tests/test_cli_contracts.py` |
| The judgement tunables live in the user's `## Preferences`, and reach the scripts as flags — never as an edited constant | `references/context.md.example` §Preferences | `SKILL.md` "Tunable defaults", the two scripts' constant blocks |
| Workspace resolution is anchored on the install shape, not a depth; a plugin's own root is never a workspace | `TESTING.md` §"Workspace resolution is anchored on the install shape, not on a depth" | `scripts/skill_config.py` `_install_workspace()` docstring, the two install-shape tests in `tests/test_config_seam.py`, `CHANGELOG.md` |
| The `scripts/` prefix is resolved from the directory `SKILL.md` was read from, never written down | `SKILL.md` "Running the scripts" | the repo-level `tests/test_install_scripts.py` guards, the `setup` skill's "Finding the files this skill needs" (which resolves a *sibling* skill the same way, `daily` or `billables-daily` by install shape) |
| Standing the pipeline up for the first time is the `setup` skill; `references/setup.md` is the mid-run diagnostic for a prerequisite that failed on a machine already working | the `setup` skill's `SKILL.md` | `SKILL.md` "When to invoke", `references/setup.md` header, `AGENTS.md`, `README.md`'s install section |
| An allow-list ask names the task and the interpreter and script paths read back off the registered task — never a folder-wide exclusion — and a block is evidenced before it is escalated | the `setup` skill's `references/endpoint-security.md` | `README.md`'s endpoint-security note, the `setup` skill's Step 5 "If it fails" |
| The browser extension's ID, which is what a managed browser's `ExtensionInstallAllowlist` takes | the `setup` skill's `references/endpoint-security.md` §"The browser extension" | the `setup` skill's Step 2, `README.md` step 2 |

The `--cover` pair has already drifted once and cost a re-run — `TESTING.md` has the
entry. The fix at the time touched the checklist copy and missed the owner.

Don't write exclusivity claims ("this is the only place that says X") into any of these
files. They enforce a snapshot and rot silently into something that still reads as
authoritative.

## When you don't maintain this copy

This file assumes you can change the skill and ship it. A user who installed it from the
repo cannot, and three of three test agents handed a genuine script defect came looking
*here* for the route upstream — the filename reads like it covers that, and it doesn't.
`references/reporting-issues.md` owns that path.

## Releasing

There is one copy: this repo is the plugin, and installing it is `/plugin install`. A
change ships by being committed here — nothing to propagate, no second leg to verify, and
no marker inside the skill to keep in step.

Bump `version` in `.claude-plugin/plugin.json` and add the matching `## [x.y.z]` heading to
`CHANGELOG.md` in the same change — those two are what `tests/test_distribution.py` holds
together, and it fails when they disagree. A user on the shared Agent Skills
export re-runs the export to update; it is generated from this plugin every time, so their
copy cannot be a stale fork of it.

Add an `### Upgrading` section to that changelog entry whenever the update alone is not
enough — a setting that has to move, a script to re-run, a scheduled task pointing at a path
the change invalidates. An update installs itself; anything a user has to do by hand is
invisible until the run that needed it fails, and by then the release notes are weeks back.

Then tag it, so the version is a commit somebody can check out and not only a heading:

```
git tag -a vX.Y.Z -m "X.Y.Z — one line"
git push origin vX.Y.Z
```

`git push` does not carry tags, which is why the second line is there. Tag the last commit
of that version rather than the one that bumped the manifest, if cleanup followed it.
