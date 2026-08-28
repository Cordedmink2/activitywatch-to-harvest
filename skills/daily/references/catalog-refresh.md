# Catalog refresh

The skill relies on cached catalogs in `Work/.mcp/`. They're cached because the underlying APIs are slow (Harvest pagination, ticket-store queries) and the data changes slowly. Refresh when stale.

## When to refresh

- Cached file is missing → refresh
- `.mtime` is older than 7 days → refresh
- The user mentions a project / ticket the catalog doesn't have → refresh
- A classification fails to find a matching `project.code` even though the ticket pattern looks valid → refresh

## Harvest project assignments

**Endpoint:** `GET https://api.harvestapp.com/api/v2/users/me/project_assignments?per_page=100&page=<N>`

**Why this endpoint specifically:** many users' Harvest PATs are *member-scope* (`expenses:read:own`, `timers:read:own/write:own`). Admin endpoints like `/projects` and `/clients` return 403 for member-scope tokens. The `/users/me/project_assignments` endpoint is self-scoped and returns the same shape — project + client + task_assignments — for projects the authenticated user is personally assigned to. Works on both member and admin tokens.

**Auth headers:**
```
Harvest-Account-ID: <user's account id>
Authorization: Bearer <HARVEST_API_KEY>
User-Agent: <something descriptive>
```

The token comes from wherever it was configured — the plugin's declared configuration, or a copied-in install's `.env` (see `references/setup.md` § "First-run: configuration"). `scripts/refresh_catalogs.py` resolves it through the same shared `harvest_client.load_creds()` helper the other Harvest scripts use, so configuring it once covers everything.

**Pagination:** loop pages at `per_page=100` until `next_page` is null. Most consultants have <1000 assignments total.

**Output:** save raw page JSON to `.mcp/harvest_assignments_p<N>.json` (and `harvest_assignments.json` for page 1). Don't reformat — downstream readers expect Harvest's shape.

**Read-replica lag (important).** This endpoint is eventually consistent: identical back-to-back requests can hit a fresh replica or a lagging one, and the lagging one can even report the new `total_entries` while still serving stale rows. So a single refresh — and the row count — are NOT reliable for a *just-created* project. No client-side trick fixes a bulk pull. To bill against a brand-new project, call `refresh_catalogs.wait_for_project(code)`, which polls across minutes (each read re-rolls the replica) and returns the assignment dict once the code surfaces. Don't treat a one-off miss as failure.

## User-specific ticket catalogs (optional)

If the user maintains a ticket dump (e.g. an active-incidents list from a CRM, a Jira/Linear export), `scripts/refresh_catalogs.py` can refresh it. The exact query is user-specific — see `.context.md` for the user's ticket-source configuration.

The script's design assumes:
- Output goes to `.mcp/<catalog>.txt` or `.mcp/<catalog>.json`
- Format is tabular text or JSON — readable line-by-line by downstream classifiers
- Auth uses whatever CLI the user has configured for their backend (e.g. `pac` CLI for Dataverse, `gh` for GitHub Issues)

## Creating a backend ticket/case to bill against

Sometimes a block belongs to new work with no Harvest project yet — the user creates a ticket/case in their backend CRM, which syncs to Harvest as a new project (`project.code` == the ticket id). For Dataverse (user's URL lives in the workspace `.env`):

> **Note:** `create_incident.py` and `read_incidents.py` below are NOT part of this skill's `scripts/` — they live in the user's Dataverse **workspace** `scripts/` directory (alongside that workspace's `auth.py` and `.env`). `<workspace>` in the commands below is `TIMESHEET_WORKSPACE`; spell the path out rather than running a bare `scripts/…`, which resolves against the skill folder. If they're missing, ask the user to sync them from their workspace before using this path.

- **Create the case with the tested helper, not a raw API call:**
  ```
  python "<workspace>/scripts/create_incident.py" --customer "<client>" --title "<title>"        # dry run — resolves client, prints what it would create
  python "<workspace>/scripts/create_incident.py" --customer "<client>" --title "<title>" --yes  # actually creates it, prints the ticket number
  ```
  It resolves the client name → account GUID, creates the Case via the Dataverse SDK, and reads back the auto-assigned ticket number. The **customer account determines the ticket prefix**, so you only supply client + title — don't try to set the number. That governs *creating* a case. Going the other way — resolving an observed ticket number to its client — derive it by grouping `.mcp/harvest_assignments*.json` on `project.code` prefix → `client.name` rather than reading a list; `PSO` and `SLA` each span 9–14 clients, so prefix alone never decides those. It's a client-facing CRM, so confirm the resolved client + title with the user before adding `--yes`.
- **Read / look up existing cases:** `python "<workspace>/scripts/read_incidents.py"` (flags: `--customer`, `--prefix`, `--ticket`, `--search`, `--all`). This is the convenient path for ad-hoc lookups; the bulk `dv_active_incidents.txt` catalog is still built via `pac env fetch` in `refresh_catalogs.py` above.
- Under the hood both scripts authenticate via the workspace `scripts/auth.py` device-code token (reads `DATAVERSE_URL`/`TENANT_ID` from `.env`); first run needs a one-time interactive login, then the token caches and refreshes silently. Equivalent raw write is `POST …/api/data/v9.2/incidents` with `title` + `customerid_account@odata.bind=/accounts(<guid>)`.
- After creating, the new project lags in Harvest (see read-replica lag above) — use `wait_for_project(code)` to get its `project_id`/`task_id` before posting.

## Sanity checks after refresh

- Harvest file has >10 entries → looks reasonable for most consultants
- Ticket-catalog file has the expected row count and column headers → looks reasonable
- If either looks empty / wrong, restore the previous file from backup before overwriting

`scripts/refresh_catalogs.py` does all the above in one go.
