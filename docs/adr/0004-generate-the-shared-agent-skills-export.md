# ADR-0004: Generate the shared Agent Skills export from the plugin

**Status:** Accepted — 2026-08-31
**Context:** distribution. Related: [`ADR-0002`](./0002-defer-splitting-the-provider-into-its-own-plugin.md)
(the other half of "one source of truth"), issue #11.

## Context

`billables` is a Claude Code plugin, and a plugin is the only way to install it. Every other
Agent Skills client — Codex, OpenCode, Hermes, Gemini CLI and the rest — reads skills from a
different place: `~/.agents/skills/` for a user's own skills, `<dir>/.agents/skills/` for a
project's. Those users cannot install a plugin at all, so today they get nothing.

The obvious fix is to keep a second copy of the skills in the shape that directory wants. That is
the failure this whole effort exists to remove: this repo has already shipped a public copy that
drifted two weeks behind the live one, because two editable copies means one of them is stale and
nobody knows which.

The shared directory also has no namespace. It is flat — one directory per skill, no plugin above
it — so a skill installed there as `daily` says nothing about where it came from and collides with
anyone else's `daily`. The Agent Skills specification additionally requires the declared `name:` in
the frontmatter to match the skill's directory name, and the declared name is what an
activation-time consumer reads: rename the directory alone and the skill is invalid, rename neither
and it is anonymous.

## Decision

**Generate the export from the plugin, one direction, never hand-edited.**
`install/export_agent_skills.py` reads `skills/` plus the plugin manifest and writes
`~/.agents/skills/` (or a directory given to it). Nothing reads the export to decide what to write,
so a hand-edit survives exactly until the next run.

**Prefix the exported directories with the plugin name, and rewrite the declared name to match.**
`skills/daily` exports as `billables-daily`, with `name: billables-daily` in its frontmatter. The
prefix is the namespace the shared directory doesn't have, and it is the plugin name precisely
because that name is already treated as permanent (it prefixes every skill a Claude Code user
types).

**Regenerate rather than merge.** Whatever has left the plugin leaves the export too — a file, or a
whole skill that was renamed or retired, which would otherwise keep activating alongside the live
one. The one exception is an exported install's `.env`: that is the user's credentials, and it is
the only piece of their data living inside the artifact. It survives even when the skill it belongs
to is retired, leaving a directory with no `SKILL.md`, which activates nothing. Running the script
twice leaves a byte-identical tree.

**The install scripts do this and nothing else.** `install/install_skill.{sh,ps1}` shrink to
finding an interpreter and handing over, so there is no second copy path left to drift.

**The workspace resolver learns the location.** `find_workspace()` already skipped `.claude/`,
whose `skills/` sits one level below where a workspace-local install would put it; `.agents/` is
skipped for the same reason and by the same rule.

**The skill states its requirements in the frontmatter.** The spec's `compatibility` field carries
the interpreter and the activity source. A plugin user gets that from the manifest and the install
dialog; a Codex user has the frontmatter and nothing else.

## Consequences

- Users on any Agent Skills client get the same skills, from the same source, with no second copy
  for anyone to maintain.
- What they install is never a stale fork — but it is only as fresh as the last time they ran the
  script. There is no update channel in the shared directory, which is the honest cost of a flat
  unnamespaced folder with no package manager over it.
- The exported skill is *not* the plugin: it has no manifest, so no declared configuration and no
  harness credential store. Those users configure through the `.env` at the exported skill's root,
  which is why the export preserves it.
- Regeneration deletes anything else a user put inside an exported directory. A file added *into*
  one of its own exports is gone at the next run — the price of "artifact, not a second source of
  truth", and stated in the script's own output. What bounds that: each export carries a stamp, and
  only a stamped directory is a candidate for retirement, because `<plugin>-something` is a name a
  user is free to give a skill of their own and being in the neighbourhood is not evidence of
  authorship. Overwriting is the weaker case and takes the weaker signal — the stamp, or a
  `SKILL.md` sitting at the exact name this run was going to write.
- The destination moves, so an install made by the *previous* installer is left behind unprefixed
  and still activates. Deleting it is not this script's call — it may hold the `.env` the user
  filled in — so every run that finds one reports it and says what to do with it.
- `tests/test_distribution.py` asserts the export is spec-valid — prefixed directories, each
  declared name matching its directory, no scratch or secrets, idempotent regeneration — and runs
  the platform's own validator over the generated copy where it is available.

## Alternatives considered

**Keep a second, hand-maintained copy in the shared shape.** Rejected: it is the drift this repo
has already lived through, and the copy strangers install would be the one the maintainer never
runs.

**Export without the prefix, as `daily`.** Spec-valid and shorter to type, but a skill named
`daily` among a user's own skills is unattributable and collides. The prefix costs nothing except
the frontmatter rewrite, which is a five-line function.

**Symlink the plugin's skills into `~/.agents/skills/`.** Cheapest to keep current, and rejected on
portability: it needs developer mode or an elevated prompt on Windows, and the exported name would
still have to differ from the directory it points at.

**Publish to the Skills API or claude.ai instead.** Out of scope for a different reason — both
reject the `disable-model-invocation` frontmatter field, and that guard is being kept.
