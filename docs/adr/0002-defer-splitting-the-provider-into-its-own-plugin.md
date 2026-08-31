# ADR-0002: Defer splitting the timesheet provider into its own plugin

**Status:** Accepted — 2026-08-31
**Context:** whole repo. Related: [`CONTEXT.md`](../../CONTEXT.md) (the vocabulary this decision
pays for), issue #10.

## Context

`billables` is meant to work against more than one timesheet provider. Harvest is the only one
today, and the obvious design for a second is the obvious one: keep the day-reading and
classification in `billables`, and put each provider behind its own plugin — `billables-harvest`,
`billables-toggl` — so a user installs the adapter they need.

That design is not buildable on the current platform. A plugin cannot resolve a filesystem path
into a sibling plugin: `${CLAUDE_PLUGIN_ROOT}` names its own root and nothing else, so
`billables` has no supported way to run a script that lives inside `billables-harvest`. The
supported seam between plugins is **MCP tool names** — a provider plugin would have to ship an
MCP server, and `billables` would call its tools rather than a bundled script.

Standing that up now would mean building and maintaining an MCP server for a provider that is the
only provider, to satisfy a boundary no second implementation is pushing on. The cost is real and
the evidence for the shape of the boundary is not: the first genuine second provider is what
tells us which calls the seam actually needs.

## Decision

**Keep the provider adapter inside the `billables` plugin.** The `harvest_*.py` scripts, their
credentials contract and the endpoint documentation stay where they are, and stay named after the
provider they talk to, because that is what they are.

**Take the provider's vocabulary out of the layers above it instead.** The shipped rules speak
the terms in `CONTEXT.md` — block, entry, client, project, task, work kind. Provider-specific
strings arrive from declared plugin configuration (credentials, account) or from the user's own
workspace (`.context.md`, above all the work kind → task mapping). No task name of any one
account appears as a default in a shipped file.

**Revisit when a second provider exists**, and let its requirements decide whether the seam is an
MCP server, a second bundled adapter selected by configuration, or something else.

## Consequences

- A second provider is an adapter and a configuration key, not a rewrite of the rules. That is
  the whole return on this decision, and it is claimed now rather than deferred with the split.
- The plugin ships one provider's client code whether or not the user bills through it. Cheap:
  a handful of Python files with no install cost.
- `billables` cannot be installed without the Harvest adapter coming along. Acceptable while
  there is one.
- The vocabulary is enforced rather than aspirational — `tests/test_provider_neutrality.py`
  fails if a provider task name returns to the shipped rules, or if the rules name a work kind
  the glossary does not define.
- If the platform later supports resolving into a sibling plugin, the split becomes cheap and
  this ADR should be reopened rather than worked around.

## Alternatives considered

**Split now, with an MCP server per provider.** Buildable, and it is probably where this ends up.
Rejected on timing: it costs a server, a tool contract and a second install step to serve one
provider, and the contract would be designed against a single example.

**Split now, with the adapter as a bundled skill inside a provider plugin, called by path.**
Not buildable — that path does not resolve. This is the specific platform constraint that dates
this ADR.

**Do nothing.** Leaves one Harvest account's task names shipped as everybody's defaults, which
is the failure a second provider would hit first, and which costs nothing to fix now.
