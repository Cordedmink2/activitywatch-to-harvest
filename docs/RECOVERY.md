# Recovery record - 2026-08-28

A firmware update caused unflushed writes to be lost. Five untracked paths created in this
repo between 09:13 and 10:07 on 2026-08-28 were destroyed before they were ever committed.
This file records what was recovered, what was not, and where the rest of the work lives.

## Recovered

| File | Recovered | Original | Note |
|---|---|---|---|
| `CLAUDE.md` | 219 B | 219 B | Complete, byte-exact |
| `AGENTS.md` | 409 B | 682 B | Head only; tail lost mid `### Triage labels` |
| `INTENT.md` | 448 B | 1779 B | Head only |
| `CONTEXT.md` | 0 B | 2485 B | **Lost entirely** - never displayed in any surviving record |

## Lost entirely - bodies of all eight docs/ files

Only the filenames survive. The ADR titles carry the decisions:

- `docs/adr/0001-the-plugin-is-the-only-copy.md`
- `docs/adr/0002-one-plugin-now-mcp-providers-later.md`
- `docs/adr/0003-named-billables-not-timesheet.md`
- `docs/adr/0004-two-channels-one-of-them-generated.md`
- `docs/adr/0005-the-setup-skill-replaces-llms-txt.md`
- `docs/agents/domain.md`
- `docs/agents/issue-tracker.md`
- `docs/agents/triage-labels.md`

## Not lost

The spec and its tickets were pushed to GitHub Issues and are unaffected:

- Issue #2 - the spec, "Turn the repo into the billables plugin: distribution,
  configuration, multi-harness, and redaction" (18,785 characters)
- Issues #3 to #15 - thirteen implementation tickets, all labelled `ready-for-agent`

Per `AGENTS.md`, issues and specs live in GitHub Issues via the `gh` CLI, which is why
they survived: they were never local-only files.

## Rebuilding the rest

`CONTEXT.md` and the eight `docs/` bodies must be regenerated, not recovered. The five ADR
titles above, `INTENT.md` and the spec in issue #2 together carry enough of the reasoning
to rewrite them. Commit them when they exist - that is the failure this file records.
