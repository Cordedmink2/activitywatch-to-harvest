# AGENTS.md

Steering for agents **working on this repo**. If you are instead helping a user *install* the
billables plugin on their machine, this is not the file you want: the two `/plugin` commands in
[`README.md`](./README.md) get it installed — or, on a harness that cannot install a plugin,
`install/install_skill.{sh,ps1}` generates the shared Agent Skills export from a clone. Either way
the plugin's own `setup` skill walks the manual steps from there, verifying each one.

## Agent skills

### Issue tracker

Issues and specs live in this repo's GitHub Issues, via the `gh` CLI. See
[`docs/agents/issue-tracker.md`](./docs/agents/issue-tracker.md).

### Triage labels

The five canonical roles, with label strings unchanged. See
[`docs/agents/triage-labels.md`](./docs/agents/triage-labels.md).

### Domain docs

Single-context: `CONTEXT.md` and `docs/adr/` at the repo root. See
[`docs/agents/domain.md`](./docs/agents/domain.md).
