# ADR-0006: Keep the provider in-plugin, but behind a command contract

**Status:** Accepted — 2026-09-02. **Supersedes [ADR-0002](./0002-defer-splitting-the-provider-into-its-own-plugin.md).**
**Context:** whole repo. Related: [`CONTEXT.md`](../../CONTEXT.md),
[ADR-0007](./0007-two-boundaries-the-provider-writes-the-sources-read.md), issues #33, #35.

## Context

ADR-0002 reached the right decision — keep the Harvest adapter inside `billables` — for a reason
that is no longer true, and a future reader acting on that reason would be misled. This ADR keeps
the decision, replaces the reasoning, and adds the part ADR-0002 left out.

**What ADR-0002 said.** A plugin cannot resolve a filesystem path into a sibling plugin, so the only
supported seam between two plugins is MCP tool names. Standing up an MCP server for the only
provider there is, against a contract designed from a single example, was not worth it.

**What has changed on the platform.** Two things, both documented:

- `plugin.json` supports a **`dependencies`** field with semver constraints. Installing a plugin
  resolves and installs its dependencies automatically, and enabling one enables them at the same
  scope. `claude plugin prune` removes orphans. So "a second install step" and "`billables` cannot
  be installed without the Harvest adapter coming along" — two of ADR-0002's listed costs — are no
  longer costs.
- A plugin's **`bin/` directory is added to `PATH`** while that plugin is enabled. So one plugin's
  skill can invoke another plugin's executable *by name*, with no path resolution. An adapter plugin
  would ship a CLI, not an MCP server.

The split ADR-0002 called unbuildable is buildable. Its central claim — "the supported seam between
plugins is MCP tool names" — is now wrong.

## Decision

**Keep the provider adapter inside the `billables` plugin.** Unchanged from ADR-0002, and everything
that decision bought stays bought: the shipped rules speak the glossary's terms, and provider strings
arrive from configuration or the user's workspace, enforced by `tests/test_provider_neutrality.py`.

**But make the boundary real, as a command contract.** The five operations — post, patch, lookup,
list, refresh — get a deliberate command-line surface with no provider wire-format field name in it,
and everything above the adapter goes through it. The adapter's files move behind that contract, into
`scripts/provider/harvest/`.

**Shape the contract as if it were `bin/`.** Commands with arguments, not file paths with flags, so
that the eventual split is a rename rather than a redesign.

**Do not adopt `bin/` yet.** The shared Agent Skills export has no manifest and no plugin, so nothing
puts a `bin/` directory on its `PATH`. Adopting it now would break that channel to buy an indirection
worth nothing while there is one plugin.

**Revisit at the second provider,** as ADR-0002 said — but revisit a rename, not a design.

## Consequences

- The one objection in ADR-0002 that survives is the one that now carries the decision: a seam
  designed against a single implementation is a guess. Building the contract in-plugin means the
  guess is cheap to correct, because correcting it touches files in one repository rather than a
  published tool surface.
- The confirmation gate stops being implemented once per write script and becomes one implementation
  in the contract. That is the largest immediate return, and it is why #22 belongs to this work.
- `harvest_post.py` currently imports `aw_client` for timezone arithmetic. An adapter that reaches
  into the activity-source client is not behind a boundary, so those helpers move to a shared
  `timezone.py` first (#36).
- `reconcile` reaches the adapter across a sibling directory by path today. It moves onto the same
  contract `daily` uses (#31).
- The export channel constrains the seam. Any future adoption of `bin/` has to answer for it, or
  accept that the export loses the provider.
- **One platform fact is still missing, and the split needs it.** Whether one plugin's scripts can
  see another plugin's declared `userConfig` is undocumented. An adapter plugin owning its own
  credentials would declare them itself, which is probably fine — but "probably" is not a seam.
  Establish it before splitting, not during.

## Alternatives considered

**Split into `billables-harvest` now.** Buildable today via `dependencies` + `bin/`, which is the new
fact this ADR exists to record. Rejected on the same timing argument ADR-0002 used, which survives
the platform change intact: with one provider there is nothing to test the contract against, and a
published cross-plugin surface is far more expensive to change than an internal one. This is where
it ends up; the trigger is a second provider, not a platform capability.

**Adopt `bin/` inside the single plugin now.** Attractive — it is the exact seam a split would use,
and adopting it early means the split changes no instruction text. Rejected because the shared Agent
Skills export has no plugin and therefore no `bin/` on `PATH`, and losing an install channel to
pre-pay for a move that may not happen is the wrong trade.

**Leave the adapter as five loose scripts.** What ADR-0002 effectively left in place. Rejected: it
puts the confirmation gate in five places, lets `reconcile` reach across a directory by path, and
means "a second provider is an adapter, not a rewrite" is a claim with nothing behind it.
