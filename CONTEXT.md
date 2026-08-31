# CONTEXT.md

The vocabulary this project uses. Two services are in play today: ActivityWatch records what
happened on the machine, Harvest holds the billed time. Both are meant to be swappable, and the
terms below are how the rules talk about them — so that a second provider is an adapter rather
than a rewrite.

**What this asks for is precise, and it is not "delete the word Harvest".** A rule may name the
product where the product is the subject: "Post to Harvest", "no Harvest write without explicit
confirmation", the endpoint documentation. What a rule may not do is bake in one Harvest
*account's strings* — a task name, a project name, a client name — because those are one user's
facts and every user's differ. That is the line the glossary draws and
`tests/test_provider_neutrality.py` enforces.

The provider half of the abstraction is done to that line; the activity-source half is not, and
this file says so below rather than pretending otherwise.

Use these words in issue titles, test names, skill instructions and reference documents. Where a
term below and a synonym both read fine, the term below wins; the synonyms are what drift looks
like.

Decisions that shaped this vocabulary are in [`docs/adr/`](./docs/adr/) — ADR-0002 for why the
provider stays inside this plugin for now.

## The two services

**Activity source** — the local service recording window titles, AFK state and browser tabs.
ActivityWatch today, reached at the configured `TIMESHEET_ACTIVITY_URL`. Unlike the provider, this
one is *not* yet abstracted: the rules name ActivityWatch's buckets, its event schema and its
categories throughout, and `references/activitywatch.md` documents its API directly. The term
exists so that work has somewhere to start, not because it is done.

**Timesheet provider**, or just **provider** — the service that holds billed time and invoices
from it. Harvest today, reached with the credentials in declared plugin configuration.
Everything the provider names — its projects, its tasks, its clients — is *its* vocabulary, not
this project's. Those strings reach a run from configuration or the user's workspace. They are
never a default in a shipped file, because one account's task list is one user's fact.

**Workspace** — the user's own directory (`TIMESHEET_WORKSPACE`), holding `Timesheets/.context.md`,
the cached catalogs under `.mcp/`, and any exports. The plugin holds no user data; the workspace
holds nothing generic.

## Reading a day

**Day skeleton** — the deterministic boundaries derived from AFK data: `work_start`, `work_end`,
breaks, active spans, and each span's `active_ratio`. Arithmetic, not judgement, and taken
verbatim.

**Signal** — an observable in the activity data that points at a client: a work-item number, a
browser profile, an environment URL, an editor workspace, a repo path, a meeting participant.

**Work item** — the identifier the work is tracked under in the user's own backend: a ticket,
case, story or bug. The highest-confidence signal there is, and what an entry's note should name.

**Switch point** — the instant inside a stretch where the client evidence changes. A real
boundary even when no break falls there.

## What gets billed

**Block** — a proposed span of the day with one attribution. Local, reviewable, not yet billed.
Blocks are what a run drafts and the user corrects.

**Entry** — a block that has been recorded with the provider. Billed. The distinction is
load-bearing: a block can be redrawn freely, an entry is out in the world and changing one is a
separate write the user has to approve again.

**Attribution** — what a block still needs: client, project, task, billable or not, and a
confidence rating.

**Client** — who the work is for.

**Project** — the provider's unit that a client's work bills to. Carries a **project code** where
the user's backend syncs one.

**Task** — the provider's sub-category of work within a project, and where the authoritative
`billable` flag lives. A task's *name* is the provider's string; a task's *meaning* is a work
kind.

**Work kind** — the neutral category of what a block was. The rules decide the work kind from the
evidence; the user's `.context.md` maps work kind → the task their provider actually offers.
Seven, and only these seven:

| Work kind | The block was |
|---|---|
| `Meeting` | a call or meeting |
| `Development` | writing or changing code, configuration, builds, deployments, bug fixes |
| `Documentation` | docs, wiki, proposal or statement-of-work writing |
| `Project management` | planning, backlog grooming, coordination |
| `Testing` | testing, QA, smoke tests |
| `Investigation` | sustained read-only analysis with no edits at all |
| `Internal admin` | the user's own overheads — timesheets, internal tooling, training |

**Assignment catalog** — the cached list of the projects the user may bill to and the tasks
assigned to each, pulled from the provider into `.mcp/`. The authority on which tasks exist and
which are billable.

**Exclusion** — a stretch deliberately not billed, declared as such rather than silently absent.

**Confidence** — `HIGH` / `MEDIUM` / `LOW`, the rating a block carries into review. `LOW` is
flagged 🔸 and asked about.

## Words to avoid

Habits, not prohibitions — the rule above (no account's strings) is the hard one.

| Don't write | Write |
|---|---|
| "Harvest entry", "Harvest task", "Harvest project" | entry, task, project |
| "Harvest note" | the entry's note |
| "timesheet line", "time entry row" | entry |
| "time chunk", "segment", "slot" | block |
| "category" for what a block was | work kind (the activity source's own `category` keeps that name) |
| "ticket" as the general term | work item ("ticket" is fine where the user's backend calls it one) |

So: naming Harvest is right where the subject genuinely *is* Harvest — the `harvest_*.py` scripts,
their credentials contract, the declared configuration keys, the endpoint documentation, and the
workflow steps that post to it. Reaching for one of its task names in a rule about how to read a
day is the drift this file exists to stop.
