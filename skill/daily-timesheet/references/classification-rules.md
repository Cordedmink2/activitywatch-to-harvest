# Classification rubric

Goal: for each proposed time block, pick a `(client, project_id, task_id, billable)` tuple and a `confidence` rating.

**`Timesheets/.context.md` is the source of truth.** It holds the per-user facts:
- Active client profiles + signals (Edge profile names, URLs, ChatGPT projects, VS Code workspaces, repo paths, SharePoint subdomains, ticket-number prefixes)
- Internal-colleague + external-contact names
- Billing conventions (description style, default tasks, the "bill by ticket not by window" rule, etc.)
- Personal-browsing exclusions
- Preferences (AFK threshold, lunch window, timezone, etc.)

This file contains only the **generic heuristics** for *applying* `.context.md` to event data. If a rule below contradicts `.context.md`, `.context.md` wins.

## Signal hierarchy (most → least reliable)

### 1. Ticket-number match (HIGH confidence)

If any window title, URL, or terminal task name within the block contains a string matching the user's ticket pattern (typically `[A-Z]{2,4}\d{3,}S?` — but check `.context.md` for the exact regex if customised):

1. Look up the prefix in `.context.md` "Ticket prefixes" / "Active client projects" sections to identify the client.
2. Look up in `.mcp/harvest_assignments*.json` matching the same string against `project.code` to get `project.id` and `task_assignments[]`.
3. If the user maintains a ticket-catalog file (e.g. a dump of active incidents), look up the title there for the description.
4. Direct hit → HIGH confidence.

**Caveat — ticket existence ≠ today's billing target.** A ticket-catalog lists *all* known incidents; thematic match isn't billing match. The user may be supporting a colleague's ticket, doing release-level work that bills to a different project, or working on something not yet ticketed. When the work item isn't named explicitly in window/URL titles, ask — don't pick the most "thematically matching" entry from the catalog.

A trailing `S` (or other suffix) on a ticket number often indicates **Support work** — check `.context.md` for the user's convention. If so, tag the description as `[Support]` but use the same `project_id` / `task_id`.

### 2. Edge profile in window title (HIGH confidence for browser activity)

Windows ending in `… - <ProfileName> - <UserDisplayName> - Microsoft Edge` (or older format `… - <ProfileName> - Microsoft Edge`): the profile name maps directly to a client. See `.context.md` "Active client projects" sections for the current profile → client mapping. If a profile isn't listed there but window content otherwise indicates a known client, follow the content signal. New profiles → propose adding them to `.context.md`.

### 3. Teams chat / call titles (HIGH confidence for Teams events)

Teams windows follow this pattern: `Chat | <Name>[, <Name>…] | <TenantName> | <user-email> | Microsoft Teams`.

- Title contains an **internal-colleague** name (see `.context.md` "Internal colleagues") → *probably* internal, but **don't auto-classify a meeting as internal just because the participants are all colleagues**. Internal teammates regularly hop on calls to discuss client work. Before billing to the internal-admin project, peek at a screenshot during the meeting to check the shared screen / agenda — if it shows a client environment, architecture diagram, ticket, or repo, bill the meeting to *that* client's project instead. Only fall back to internal-admin when the screenshot shows internal artefacts (internal wiki, Adaptable CRM, AI training material, timesheet work) or is genuinely unrevealing.
- Title contains a **known external contact** (see `.context.md` "Known external contacts") → use the mapped client. The `(External unfamiliar)` Teams flag is often stale; treat it as a soft warning, not a hard rule.
- Title contains an **unrecognised external** with no client signal → ask the user; don't auto-classify.
- **Recurring meeting names** → see `.context.md` "Notes on inference" or "Recurring meetings" for the user's canonical attribution.

### 4. App-stack signal (MEDIUM confidence)

VS Code workspaces, Obsidian vaults, repo paths, ChatGPT project names, and other app signatures map to **codebases** that belong to a client — see `.context.md` for the current mapping.

**Codebase ≠ Harvest project.** A single client codebase can serve multiple Harvest projects. The repo path tells you the client family; the work item context (active ticket, commit message, who's being supported, what's being released) tells you the specific Harvest project.

### 5. URL pattern (MEDIUM confidence)

URLs in browser tabs (Edge / Firefox / Chrome) expose Dynamics environments, Azure DevOps orgs, SharePoint subdomains, ChatGPT project slugs, etc. — see `.context.md` for the user's URL → client mapping. The URL fingerprint is usually unambiguous; if a new URL pattern appears that maps to a known client, propose adding it to `.context.md`.

### 6. `claude.exe` / terminal adjacency rule

Pure `claude.exe` / `WindowsTerminal.exe` (or other AI-assist clients) — apply the surrounding-context rule:

- Pure terminal time adjacent to a client app stack → attribute to that client.
- Terminal adjacent to timesheet-automation paths (`Claude/Scheduled/`, `Pictures/WorkScreenshots/`, `Timesheets/`) → the user's internal-admin project.
- Claude Code task names visible in terminal titles (e.g. `✳ <slug>`) are useful signals but **the slug usually names a feature, not a client** — e.g. `hardcode-confidential-team-lookups` tells you *what* is being worked on, not *who* it's for. Triangulate with the surrounding Edge profile, repo path, or open Dataverse environment to pin the client. If the slug is the only signal you have and you can't triangulate, flag the block 🔸 and ask.

## Task (Harvest sub-category) selection

The user's default task (and any per-project conventions) live in `.context.md`. Generic fallback mapping (used when `.context.md` doesn't override):

| Block content | Task choice |
|---|---|
| Mostly Teams meeting / call | `Gen - Meeting` |
| Code / config / build / deploy | `Gen - Development/Configuration` |
| Docs / wiki / SOW writing | `Gen - Documentation` |
| Project management, planning, backlog grooming | `Gen - Project Management` |
| Testing, QA, smoke tests | `Gen - Testing` |
| Pure read-only analysis | `Gen - Investigation` |
| Harvest itself, internal admin tooling | `No Display` or NB equivalent |

If the project's `task_assignments[]` doesn't include the task you'd pick, fall back to `Gen - General Consulting`. Don't invent new tasks.

The `(NB)` variants are non-billable. Use them when the block is internal/admin/training even though it sits inside a client-coded project.

## Confidence rating

- **HIGH** — direct ticket-number hit, OR two corroborating signals (e.g. Edge profile + URL agree).
- **MEDIUM** — single signal (profile, URL, or app), no contradictions.
- **LOW** — conflicting signals, or signal absent but block is non-trivial duration. Mark with 🔸 and ask the user.

## Exclusions (NEVER bill)

See `Timesheets/.context.md` "Personal browsing patterns to exclude" (or equivalent section). Apply per the source of truth.
