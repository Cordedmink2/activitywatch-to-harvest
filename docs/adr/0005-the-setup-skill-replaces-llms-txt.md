# ADR-0005: The setup skill replaces `llms.txt`

**Status:** Accepted — 2026-09-02
**Context:** distribution. Related: [`ADR-0004`](./0004-generate-the-shared-agent-skills-export.md)
(the other install artifact), issues #12 and #14.

## Context

There were two ways to install this. The plugin — `/plugin marketplace add`, `/plugin install` —
and `llms.txt`, a 225-line runbook a user pasted a prompt about and an agent followed top to
bottom: clone the repo, probe the interpreter, install ActivityWatch, the extension, the profile
tags, the category rules, run the scaffold script, create `.env`, register the screenshot task.

Two install paths drift. That is not a prediction; this repo has already shipped a public copy two
weeks behind the live one, and the reason it went unnoticed is that the maintainer used one path
and strangers used the other. `llms.txt` had the same shape: a hand-maintained description of what
the plugin does, next to the plugin, with nothing holding the two in step. It had already been
wrong in the way that costs a user an afternoon: through 0.4.4 it stated flatly that ActivityWatch
was not on winget, which it is.

The runbook also carried something the plugin did not: the manual steps. Installing the activity
source, the browser extension, the per-profile title tags, the category rules and the screenshot
task are things only a person can do, and `llms.txt` was the only place they were written for an
agent to follow. Deleting it before that existed elsewhere would have removed the useful half.

Alongside it, `skills/daily/VERSION` recorded the shipped version a second time, and a publish
script propagated between the three copies the repo used to keep. Both belong to the same
arrangement: markers and rituals whose whole job was keeping copies in agreement.

## Decision

**`/billables:setup` owns the manual steps, and `llms.txt` is deleted.** The skill covers the human
residue and nothing else — the activity source, the extension, the profile tags, the category rules,
the screenshot task — with a check after each step that has to come back before the next one starts.
That check is the reason it is a skill rather than a shorter runbook: every one of those steps can
look like it worked and have done nothing, and the symptom arrives days later as an empty timesheet.

**The plugin is the only way in.** The install section of the README is the two `/plugin` commands
and then `/billables:setup`. The shared Agent Skills export (ADR-0004) is the same skills from the
same source, for harnesses that cannot install a plugin — not a second path, an artifact of the
first.

**The version lives only in the plugin manifest.** `skills/daily/VERSION` is deleted along with the
parity test that compared it to the changelog. `export_agent_skills.py` already read the manifest to
print the version it exports, so nothing needed a replacement. `tests/test_distribution.py` holds the
manifest against the changelog heading, and that pair is the whole release.

**Nothing describes the three-copy ritual.** The publish script is gone, and so are the instructions
that named it — `references/self-development.md` §Releasing and the `Files in this skill` entry for
`VERSION`.

**The README keeps its prose walkthrough.** Deleting it too would leave someone who has not
installed anything with no way to judge the tool before adopting it. It is marked as the reading
version of what the skill runs, and it is not a second procedure to follow: the steps it duplicates
are the ones a person performs by hand either way.

## Consequences

- One install path, so there is nothing for a second one to drift from — the failure this whole
  effort removes, rather than the same failure in a new shape.
- The manual steps are now *verified* rather than described. A step blocked by endpoint security is
  caught where it happens and produces a specific allow-list request, instead of failing silently
  and surfacing days later.
- A user with no plugin marketplace access loses the paste-a-prompt route. They run the export
  (`install/install_skill.{sh,ps1}`) from a clone and get the same `setup` skill in it, so the
  capability survives; what is gone is the zero-clone shortcut, which was the drifting copy. That
  only holds if they are told it is there — README step 5 names all three exported directories for
  this reason, having previously named only `billables-daily`.
- The version has one home. Bumping it is one edit, and `tests/test_distribution.py` fails if the
  changelog disagrees.
- One step had no other agent-readable home and moved rather than went: scaffolding the workspace.
  The `setup` skill defers it to the `daily` skill's first run, and `references/setup.md` covered
  `.context.md` but never the three directories around it — the runbook was the only place that did.
  It is now §"First-run: the workspace" there.
- An exported install carries no version marker at all. The issue form asks for the plugin's version
  instead — `/plugin` in Claude Code, or the `Exporting billables v...` line the export prints.
- `tests/test_distribution.py` guards the deletion: the two files stay gone, and nothing in an
  enumerated set of instructions — the root documents, `docs/agents/`, every `SKILL.md`, reference
  and `scripts/` file in every skill, the hooks, the installers, the issue form — may name
  `llms.txt`, `publish.ps1`, the release skill, or call any of it a runbook. The set is an
  enumeration and not "the tree minus exclusions", so it is the guard's scope rather than a claim
  about the rest of the repo: `CHANGELOG.md`, `docs/RECOVERY.md`, `docs/adr/` and `TESTING.md` are
  outside it because they record what happened, and `tests/` because a test has to write these
  names down in order to assert on them.

## Alternatives considered

**Keep `llms.txt` as a fallback for machines with no marketplace access.** The strongest case for
keeping it, and rejected on exactly the ground the ticket names: a fallback install path is still a
second install path, and it would drift in the same way for the same reason. Those users are served
by the export, which is generated rather than maintained.

**Shrink `llms.txt` to a pointer at the plugin.** Rejected as the worst of both — a file that must
still be kept current, holding nothing worth reading, and whose existence invites the next person to
put a step back into it.

**Keep `VERSION` and generate it from the manifest.** It would not drift, but it is a file to
explain, and the only consumer was a test comparing it to the changelog. The manifest is what a
marketplace displays and what the export prints; a generated echo of it earns nothing.
