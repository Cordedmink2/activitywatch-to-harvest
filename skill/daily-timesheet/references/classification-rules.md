# Classification rubric

Goal: for each proposed time block, pick a `(client, project_id, task_id, billable)` tuple and a `confidence` rating.

**`Timesheets/.context.md` is the source of truth.** It holds the per-user facts:
- Active client profiles + signals (Edge profile names, URLs, ChatGPT projects, VS Code workspaces, repo paths, SharePoint subdomains, ticket-number prefixes)
- Internal-colleague + external-contact names
- Billing-convention *overrides* (default tasks, per-project conventions, note-style examples in the user's voice)
- User-specific personal-browsing recognizers (on top of the generic exclusion categories below)
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

Windows ending in `… - <ProfileName> - <UserDisplayName> - Microsoft Edge` (or older format `… - <ProfileName> - Microsoft Edge`): the profile name maps directly to a client. (`<UserDisplayName>` is the user's Edge profile display name — discover it from window titles in the first session.) See `.context.md` "Active client projects" sections for the current profile → client mapping. If a profile isn't listed there but window content otherwise indicates a known client, follow the content signal. New profiles → propose adding them to `.context.md`.

### 3. Teams chat / call titles (HIGH confidence for Teams events)

Teams windows follow this pattern: `Chat | <Name>[, <Name>…] | <TenantName> | <user-email> | Microsoft Teams`.

- Title contains an **internal-colleague** name (see `.context.md` "Internal colleagues") → *probably* internal, but **don't auto-classify a meeting as internal just because the participants are all colleagues**. Internal teammates regularly hop on calls to discuss client work. Before billing to the internal-admin project, peek at a screenshot during the meeting to check the shared screen / agenda — if it shows a client environment, architecture diagram, ticket, or repo, bill the meeting to *that* client's project instead. Only fall back to internal-admin when the screenshot shows internal artefacts (internal wiki, Adaptable CRM, AI training material, timesheet work) or is genuinely unrevealing.
- Title contains a **known external contact** (see `.context.md` "Known external contacts") → use the mapped client. The `(External unfamiliar)` Teams flag is often stale; treat it as a soft warning, not a hard rule.
- Title contains an **unrecognised external** with no client signal → ask the user; don't auto-classify.
- **Recurring meeting names** → see `.context.md` "Notes on inference" or "Recurring meetings" for the user's canonical attribution.

### 4. App-stack signal (MEDIUM confidence)

VS Code workspaces, Obsidian vaults, repo paths, ChatGPT project names, and other app signatures map to **codebases** that belong to a client — see `.context.md` for the current mapping.

**Codebase ≠ Harvest project.** A single client codebase can serve multiple Harvest projects. The repo path tells you the client family; the work item context (active ticket, commit message, who's being supported, what's being released) tells you the specific Harvest project.

**Focused window ≠ active attention (autonomous agents + multi-monitor).** The window-watcher logs only the *foreground* window. When a Claude Code agent runs unattended (`auto mode`, a background agent) in a VS Code window, that window counts as "focused" for the agent's whole runtime — while the user's real work is a *different* client's session on another monitor. This inflates the `activity_timeline.py` rollup minutes for the agent's workspace and drops the parallel client work. Signal: a screenshot showing `auto mode on ← 1 agent` or `Waiting for … background agent to finish`. Action: when one workspace dominates the rollup on a multi-monitor day, read the *other* monitors (`_m1`/`_m3`) at that timestamp before trusting the per-category minutes, and treat that day's per-client hours as a user-confirmed split rather than a rollup readout. The same effect has a mirror image on the AFK side: a low `active_ratio` while an agent runs is supervision, not absence. Supervised agent time is billable, so check the other monitors for the agent's output before shrinking a thin block or dropping a stretch on ratio alone.

**Long agent-CLI sessions poison the window title.** A running `claude` session keeps one editor tab in focus (`CLAUDE.md`, `AGENTS.md`, a plan `.md`) for its whole duration while the actual work happens in the terminal, the browser, or on another monitor. The *file name* in such a title is not a work signal and will mis-attribute whole blocks. The VS Code *workspace* tag (`… - <Workspace> - Visual Studio Code`) stays valid, but when a block is titled with these files, resolve the client from screenshots — and check every monitor, not just the one showing the focused app. The same applies to any other `*.md` title that isn't obviously one of these three: confirm the file actually lives in the client's repo (`git log --follow -- <path>` or a plain find) before trusting it — a Claude Code skill's own reference file (methodology docs, checklists) can be open in the editor while a *different* workspace has focus, and its name alone will look like project documentation.

### 5. Environment identifier (MEDIUM confidence)

URLs in browser tabs (Edge / Firefox / Chrome) expose Dynamics environments, Azure DevOps orgs, SharePoint subdomains, ChatGPT project slugs, etc. — see `.context.md` for the user's URL → client mapping. The URL fingerprint is usually unambiguous; if a new URL pattern appears that maps to a known client, propose adding it to `.context.md`.

**The identifier is often not in the window title at all.** Admin tools that connect to a client environment — XrmToolBox, database/API clients, RDP sessions, CLI auth profiles — carry a fixed product name in the title and show the environment only on screen: a connection dropdown, a status bar, a profile list. The connected environment decides the client; the tool name never does, and neither does the workspace behind it. Two consequences: the block stays unresolved until a screenshot shows the connection (`SKILL.md` Step 5.2), and §6's adjacency rule does **not** extend here — connecting to a different environment is frequently the switch point itself, so the neighbouring block is the wrong answer by construction. Flag these on sight: a title with no visible ambiguity won't otherwise reach the screenshot check.

### 6. `claude.exe` / terminal adjacency rule

Pure `claude.exe` / `WindowsTerminal.exe` (or other AI-assist clients) — apply the surrounding-context rule:

- Pure terminal time adjacent to a client app stack → attribute to that client.
- Terminal adjacent to timesheet-automation paths (`Claude/Scheduled/`, `Pictures/WorkScreenshots/`, `Timesheets/`) → the user's internal-admin project.
- Claude Code task names visible in terminal titles (e.g. `✳ <slug>`) are useful signals but **the slug usually names a feature, not a client** — e.g. `hardcode-confidential-team-lookups` tells you *what* is being worked on, not *who* it's for. Triangulate with the surrounding Edge profile, repo path, or open Dataverse environment to pin the client. If the slug is the only signal you have and you can't triangulate, flag the block 🔸 and ask.

## Interleaved days — find the switch point, don't average

The costliest real-world misattributions are long blocks on days where the user alternated between two clients: the whole block gets billed to whichever client *dominates* the category rollup, and the other client's hours land on the wrong invoice.

**Triggers — treat the block as interleaved when any of these hold:**
- The day rollup shows ≥2 clients with ≥30 min each, and a single proposed block is >1 hr
- The zoomed timeline alternates between two clients' signals within the block
- Any `!MULTI` span, or a block titled by an agent-session file (`CLAUDE.md`, `AGENTS.md`, plan `.md`s)
- An autonomous agent ran during the block (see "Focused window ≠ active attention" above)

**Procedure:**
1. Zoom the timeline over the block (`activity_timeline.py <date> --window …`) and note every point where the client signal flips.
2. Probe screenshots economically: start with ~3 spread across the block (start / middle / end), then densify only around detected flips until each switch point is bracketed to ~10 min. Check the other monitors at every probe, and record which client's work is on screen.
3. Locate the **switch point(s)**: the boundary between runs of consistent client evidence. Split the block there. A switch point is a real boundary even with no AFK gap — client A until 16:10 and client B after is two entries, at whatever timestamps the evidence shows.
4. Attribute each sub-block to its own client. Never bill the whole block to the rollup-dominant client while a second client shows ≥15 min of evidence inside it — if the evidence can't pin the switch point, ask the user rather than averaging.
5. If the two "clients" are actually work vs. personal/upskilling/internal interleaved, the same procedure applies — carve out the non-billable or internal runs, and say so in the presentation.
6. **A named Teams meeting recurring in fragments through the block is its own sub-block** (the user attending while multitasking) — carve it out with its own attribution per signal §3, even though no single fragment is long. The parallel coding stays with its own client.
7. **Some days have no switch point to find.** Two workspaces with an agent session in each, focus alternating every 1–3 min for hours, is genuinely parallel work — step 2 will keep finding flips and never bracket a boundary. Don't manufacture one, and don't keep spending screenshots hunting it. Ask per step 4. If the user hands the split back to you ("you decide"), tally each client's minutes across the block from the zoom, allocate proportionally, and place each boundary where that client's corroborating evidence clusters (a CRM/ADO/SharePoint run, a commit, a bug fixed). A client whose fragments total under step 4's ≥15 min bar is noise — leave that time with the dominant client. Say in the presentation that the boundary is an allocation rather than an observed switch, so the user knows which kind of call they are approving.

## Task (Harvest sub-category) selection

**This table owns the activity → task mapping**; `SKILL.md` Step 4 points here rather than restating it. Resolution order:

1. **`.context.md` overrides win.** Check the user's "How I bill" / preferences section first — it typically sets a default task (e.g. `Gen - Development/Configuration`) and per-project conventions (e.g. a specific default task for the internal-admin project, or a hardcoded `project · task` pair under a client's section). A per-client hardcoded task beats the activity mapping below — e.g. if the client entry pins `Gen - Development/Configuration`, a design-doc-heavy block still bills there, not to Documentation.
2. **The task follows the block's *dominant* activity**, not its incidental surfaces. A dev block that included reading docs and a 5-min chat is still Development/Configuration. Only give a block a meeting task when the block *is* a call/meeting.
3. Generic mapping when `.context.md` doesn't decide it:

| Dominant block activity | Task choice |
|---|---|
| A Teams meeting / call | `Gen - Meeting` |
| Code / config / build / deploy / bug fixing | `Gen - Development/Configuration` |
| Docs / wiki / SOW writing | `Gen - Documentation` |
| Project management, planning, backlog grooming | `Gen - Project Management` |
| Testing, QA, smoke tests | `Gen - Testing` |
| Sustained pure read-only analysis, **no edits at all** | `Gen - Investigation` (rare — any config/code change makes it Development/Configuration) |
| Harvest itself, internal admin tooling | `No Display` or the project's NB equivalent |

4. Pick only from the project's actual `task_assignments[]` (via `harvest_lookup.py`). If the task you'd pick isn't assigned, fall back to `Gen - Issue Resolution` for investigation-type work, else `Gen - General Consulting`. Don't invent tasks.

## Billing conventions (defaults — `.context.md` overrides win)

- **Bill by ticket / work item, not by window or app.** One sustained block of work on one ticket = one Harvest entry, even when the surface switched between IDE, browser, Teams, and admin portals. Don't fragment by window-title change.
- **The timesheet run itself lands *after* the last block it can bill.** Doing the timesheet is real internal-admin time, but it happens at the end of the day — usually in the dead stretch past `work_end`, which is unbillable anyway. The failure is back-dating it onto the last live block: the day's final 20-30 min get labelled "timesheet & expenses, non-billable" while the screenshots across that window show ordinary client work, and the client silently loses the time. **Before booking any timesheet-admin entry, read a screenshot inside the window and confirm a timesheet or Harvest surface is actually on one of the monitors.** If it shows client work, bill the client; put the admin time where it really happened, or leave it off if that stretch is already excluded. Observed on 2026-08-18: 17:30-17:54 posted as internal admin, four captures across it showing NZLS access-sync work and no Harvest UI on any monitor.
- **A matching ticket/case older than ~1 week → make a NEW case, don't reuse it.** The old case is likely closed or already invoiced. Create a fresh one (`references/new-client-work.md`) and bill to that; only reuse a genuinely recent / still-open ticket.

## Writing the Harvest note (description)

Notes go to clients on invoices — `SKILL.md` carries the hard rule (client-readable, SOW test). Style defaults:

- **5–15 words, outcome-focused.** Lead with the result, not the tools or files: "Resolved the certificate import interface bug", not "Debugged CreateCertificateRequestsHandler.cs".
- **Reference the specific work item** (e.g. `US1031`, `Bug 1127`) over just the parent SOW. The numbers surface in CRM record titles, ADO URLs (`_workitems/edit/<id>`), and PR titles (`feat(SOW15 #1031): …`). Name the parent SOW only as context, never as a substitute for the work item.
- **Internal artefact names leak via the file or tool in focus — translate before writing the note.** Code file names → the client process they serve ("complaint creation process", not `ComplaintRaisedService.cs`); repo/knowledge tooling (wiki scripts, knowledge base) → the project area it serves, or "project documentation"; agent/config files (`AGENTS.md`, `CLAUDE.md`, plan `.md`s) → never named.
- The user's own voice and worked examples: `.context.md` "How I bill".

**Sourcing a work-item number: delegate the dig to a subagent.** A window title rarely names the exact US/Bug number, but `git log` in the client's repos at the block's timestamps often does, and a subagent can search several repos and a project wiki in parallel without spending the main session's context on file listings and commit dumps. Give it: the repo paths, the local-time windows in question, and what each window's window-titles/screenshots showed (so it knows what to corroborate). Tell it explicitly not to invent a number — a wrong ADO number on a client invoice is worse than a generic description — and to report its evidence (commit hash + message, or wiki doc title) alongside each finding so you can judge confidence yourself rather than trust its say-so.
- A subagent finding a file open in a workspace doesn't confirm it's that client's file — have it check the file's actual repo history, not just the window title, before citing anything from it.

**Billable status comes from the task assignment, not the task name.** `task_assignments[N].billable` in the catalog is authoritative. The `(NB)` suffix is a naming convention hint — some non-billable tasks (e.g. everything under an internal admin project) don't carry it. When the block is internal/admin/training, pick a task whose `billable: false` in the catalog.

## Confidence rating

- **HIGH** — direct ticket-number hit, OR two corroborating signals (e.g. Edge profile + URL agree).
- **MEDIUM** — single signal (profile, URL, or app), no contradictions.
- **LOW** — conflicting signals, or signal absent but block is non-trivial duration. Mark with 🔸 and ask the user.

## Exclusions (NEVER bill)

Generic categories, always excluded:

- Flight/travel searches and holiday planning
- Social media scrolling (FB / IG / X / LinkedIn), news, weather, shopping, personal email
- Pomodoro/timer overlay pages (the timer isn't the work)
- Home admin (router, smart home, NAS)

`Timesheets/.context.md` "Personal browsing patterns to exclude" adds the user's specific recognizers on top and wins on any conflict.
