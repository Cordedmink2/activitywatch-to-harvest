"""The one place the bundled scripts read their configuration.

  setting(key, flag=..., default=...) -> str | None   — a single setting
  has_value(candidate) -> bool                        — whether a candidate counts at all
  find_workspace() -> Path | None                     — the directory holding `.mcp/`
  fail_missing(message) -> NoReturn                   — the error contract for a
                                                        required setting that isn't there

This module carries the reasoning for the precedence below; the restatements of it are
registered in `references/self-development.md` § "Rules with more than one copy", so a
change here has a list of the other copies to change with it.

Precedence, highest first:

  1. **A per-command flag**, where the script offers one — overrides a single run.
  2. **The skill `.env` file** at the skill root, next to `SKILL.md`. Simple `KEY=VALUE`
     lines; blank lines and `#` comments allowed, surrounding quotes stripped.
  3. **The process environment**, which is where a harness injects values.
  4. **The script's own default**, when it documents one.

`.env` beating the process environment is the order as it has always behaved, kept
deliberately rather than reconsidered here — a prefactor is the wrong place to change
which of a user's two configured values wins.

A value that is blank or whitespace-only counts as *unset* at every layer, so it falls
through to the next one — see `has_value()`. `DATAVERSE_URL=` left behind in a copied
`.env.example` means "I don't use this", and a scheduler that passes an empty string for
an omitted argument must not thereby discard the configured value. This is a deliberate
widening: the `.env` layer already discarded blanks, because `_parse_env_file` strips,
while a whitespace-only *environment variable* used to be handed to the caller verbatim.
`TESTING.md` § "Settled decisions" records why that inconsistency was not preserved.

Nothing here is provider-specific: the keys belong to their callers, and the credentials
contract in particular stays in `harvest_client.load_creds()`. This module owns only the
question of *where a value comes from*.

No third-party deps — stdlib only, so a script that imports it stays importable on a
machine that has nothing but Python.
"""
import os
import sys
from pathlib import Path
from typing import NoReturn

SKILL_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = SKILL_ROOT / ".env"


def _parse_env_file(path: Path) -> dict:
    out = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        v = v.strip()
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            v = v[1:-1]
        out[k.strip()] = v
    return out


def has_value(candidate: str | None) -> bool:
    """Whether a candidate counts as configured. Blank and whitespace-only do not.

    Public because the rule outlives `setting()`: `harvest_lookup.find_catalog_dir`
    layers a `--mcp-dir` flag over a resolved workspace, and its flag has no settings key
    of its own to resolve through. Asking here keeps "blank means unset" to one
    implementation instead of a truth test per call site — which is how `--mcp-dir ""`
    came to beat a perfectly good configured workspace.
    """
    return bool(candidate and candidate.strip())


def setting(key: str, *, flag: str | None = None, default: str | None = None) -> str | None:
    """Resolve one setting through the precedence documented at the top of this module.

    `flag` is whatever the script's own command line supplied for it, or None. `default`
    is returned when no layer offers a value, so an optional setting can be told apart
    from a configured one — callers decide whether an unset value is fatal, and the ones
    for which it is say so through `fail_missing()`.
    """
    file_vals = _parse_env_file(ENV_PATH) if ENV_PATH.exists() else {}
    for candidate in (flag, file_vals.get(key), os.environ.get(key)):
        if has_value(candidate):
            return candidate
    return default


def fail_missing(message: str) -> NoReturn:
    """Stop because a required setting did not resolve: one `ERROR:` line, exit 1.

    Never a traceback. A model reads these scripts' output, and a traceback tells it the
    tool is broken — so it goes debugging the script instead of filling in the setting it
    was actually being asked for. `message` carries the rest: what is missing and how to
    supply it.
    """
    sys.exit(f"ERROR: {message}")


def find_workspace() -> Path | None:
    """Locate the workspace root holding the `.mcp/` catalogs, or None if it can't be found.

    The writer (refresh_catalogs.py) and the readers (harvest_lookup.py) both resolve
    the workspace through here, so a refresh cannot write catalogs into one directory
    while a lookup reads another. Resolution order:

    1. TIMESHEET_WORKSPACE, through `setting()` above — explicit wins.
    2. The current directory, if it already looks like a workspace (`.mcp/` or `Timesheets/`).
    3. The directories the skill is installed under, if one looks like a workspace. Two
       install shapes are checked: `<workspace>/skills/<name>` and Claude Code's own
       `<workspace>/.claude/skills/<name>`, which sits one level deeper. Checking only the
       first meant auto-detection could never succeed on a stock install, while
       `.env.example` promised that it would.

    Returning None instead of guessing is deliberate: deriving a path from the install
    location and using it regardless is how refreshes used to report success while
    writing catalogs nowhere the reader would look.
    """
    ws = setting("TIMESHEET_WORKSPACE")
    if ws:
        return Path(ws).expanduser()
    for cand in (Path.cwd(), *SKILL_ROOT.parents[1:3]):
        if (cand / ".mcp").is_dir() or (cand / "Timesheets").is_dir():
            return cand
    return None
