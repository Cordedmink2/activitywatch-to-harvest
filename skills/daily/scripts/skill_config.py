"""The one place the bundled scripts read their configuration.

  setting(key, flag=..., default=...) -> str | None   — a single setting
  has_value(candidate) -> bool                        — whether a candidate counts at all
  find_workspace() -> Path | None                     — the directory holding `.mcp/`
  fail_missing(message) -> NoReturn                   — the error contract for a
                                                        required setting that isn't there
  note_for_an_unreached_shell() -> str                — the cause a missing setting has
                                                        when the shell is the reason

This module carries the reasoning for the precedence below; the restatements of it are
registered in `references/self-development.md` § "Rules with more than one copy", so a
change here has a list of the other copies to change with it.

Precedence, highest first:

  1. **A per-command flag**, where the script offers one — overrides a single run.
  2. **The skill `.env` file** at the skill root, next to `SKILL.md`. Simple `KEY=VALUE`
     lines; blank lines and `#` comments allowed, surrounding quotes stripped.
  3. **The process environment**, which is where a harness injects values — for the
     commands it injects them into. Claude Code publishes them as a POSIX shell
     fragment applied to its **Bash** tool alone, so a script the model runs through
     PowerShell finds this layer empty on a machine configured perfectly well. That is
     not a fourth source to add; it is one shell missing the third, and
     `note_for_an_unreached_shell()` is what says so when a required setting is absent.
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
from typing import NoReturn, TypeGuard, overload

SKILL_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = SKILL_ROOT / ".env"

# The two variables the shell note below is decided from. Neither is read for anything
# else, and both were confirmed in the process that actually prints the message — a Python
# child of each tool, not merely the shell itself.
#
# `CLAUDECODE` is set by Claude Code in every tool process, in both shells, so its absence
# means an ordinary terminal: nothing was published there for any shell to have missed,
# and the note would be a wrong hint. `MSYSTEM` is set by Git Bash and by nothing else on
# Windows, so its absence *inside* a session is the tell that the command did not come
# from the Bash tool.
IN_A_SESSION = "CLAUDECODE"
POSIX_SHELL_MARK = "MSYSTEM"

# A harness's own directory, which holds its `skills/` one level below where a
# workspace-local install would put it: `.claude/` is Claude Code's, `.agents/` is the
# shared Agent Skills location the other harnesses read and where the export lands.
HARNESS_DIRS = {".claude", ".agents"}


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


def has_value(candidate: str | None) -> TypeGuard[str]:
    """Whether a candidate counts as configured. Blank and whitespace-only do not.

    Public because the rule outlives `setting()`: `harvest_lookup.find_catalog_dir`
    layers a `--mcp-dir` flag over a resolved workspace, and its flag has no settings key
    of its own to resolve through. Asking here keeps "blank means unset" to one
    implementation instead of a truth test per call site — which is how `--mcp-dir ""`
    came to beat a perfectly good configured workspace.

    A `TypeGuard` rather than a plain `bool` so a caller that guards on this is known to
    be holding a real string afterwards. That is what the check means; saying so keeps
    the callers from having to repeat it.
    """
    return bool(candidate and candidate.strip())


@overload
def setting(key: str, *, flag: str | None = ..., default: str) -> str: ...
@overload
def setting(key: str, *, flag: str | None = ..., default: None = ...) -> str | None: ...


def setting(key: str, *, flag: str | None = None, default: str | None = None) -> str | None:
    """Resolve one setting through the precedence documented at the top of this module.

    `flag` is whatever the script's own command line supplied for it, or None. `default`
    is returned when no layer offers a value, so an optional setting can be told apart
    from a configured one — callers decide whether an unset value is fatal, and the ones
    for which it is say so through `fail_missing()`.

    The two overloads above say the same thing to a type checker: a caller that supplies
    a `default` cannot be handed None, and one that does not must expect it. Without them
    every caller of the first kind looks like it is about to use an optional value, which
    buries the callers where the possibility is real.
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


def note_for_an_unreached_shell(platform: str | None = None, environ=None) -> str:
    """The extra cause a missing-setting message carries when this process is one the
    published configuration could not have reached. An empty string when it isn't.

    A harness publishes the declared values by writing a POSIX shell fragment, and Claude
    Code applies that to its **Bash** tool alone — its PowerShell tool is given no
    equivalent and loads no profile. So on Windows a script the model happens to run
    through PowerShell reports the timezone or the credentials missing on a machine that
    is configured perfectly well, and the message it prints sends the user off to start a
    new session or install Git Bash. Neither is the fix here, and following either costs
    them the run. `TESTING.md` § "Two ways the configuration does not arrive" carries the
    evidence and the mechanisms that were rejected before settling on saying so.

    Deliberately not a *detection of PowerShell*. What is checked is the absence of the
    POSIX shell's own marker, which is equally true of `cmd.exe` and of anything else that
    is not Git Bash — and the answer for all of them is the same one.

    Both inputs are parameters because the branch is Windows-only: a suite that could
    reach it only by being run on Windows *through the PowerShell tool* would never reach
    it, so the four cells are driven by argument instead.
    """
    platform = sys.platform if platform is None else platform
    environ = os.environ if environ is None else environ
    if platform != "win32":
        return ""
    if not environ.get(IN_A_SESSION) or environ.get(POSIX_SHELL_MARK):
        return ""
    return (
        "\n  This command did not come from the Bash tool, and that is the only shell the\n"
        "  configured values reach — they are published as a POSIX shell fragment, so\n"
        "  PowerShell reports them missing however well this machine is configured.\n"
        "  Re-run the command through the Bash tool. If there is no working Bash tool\n"
        "  here, Git Bash is not installed and nothing was published to either shell.")


def _looks_like_a_workspace(candidate: Path) -> bool:
    return (candidate / ".mcp").is_dir() or (candidate / "Timesheets").is_dir()


def _install_workspace() -> Path | None:
    """The workspace this skill is installed *inside*, if its install shape has one.

    Anchored on the shape rather than on a depth. The skill has to sit directly inside a
    `skills/` directory, and the candidate is that directory's parent — with the harness
    directories `.claude/` (Claude Code) and `.agents/` (the shared Agent Skills location
    every other harness reads) skipped, because their skills directories sit one level
    deeper than a workspace-local one.

    A depth is the thing that must not be guessed here. The walk this replaces took two
    arbitrary ancestors and accepted whichever first looked workspace-shaped, so any
    install nested one level further than expected resolved to whatever real workspace
    happened to be above it — a public checkout inside `~/Admin` resolved to `~/Admin`.
    Nothing fails at that point: the refresh reports success, and the stale catalogs
    surface days later. `TESTING.md` § "Workspace resolution is anchored on the install
    shape, not on a depth" owns the record.

    A plugin install is the third shape, and the reason this is a rule rather than one
    more depth to add: `<plugin>/skills/<name>` matches the first shape exactly, while the
    directory above it is the harness's plugin cache, or whatever a clone happens to sit
    inside. The plugin holds no user data, so its own root is never the workspace, and
    `.claude-plugin/` beside the skills directory is what identifies one.
    """
    parent = SKILL_ROOT.parent
    if parent.name != "skills":
        return None
    root = parent.parent
    if root.name in HARNESS_DIRS:
        root = root.parent
    if (root / ".claude-plugin").is_dir():
        return None
    return root if _looks_like_a_workspace(root) else None


def find_workspace() -> Path | None:
    """Locate the workspace root holding the `.mcp/` catalogs, or None if it can't be found.

    The writer (refresh_catalogs.py) and the readers (harvest_lookup.py) both resolve
    the workspace through here, so a refresh cannot write catalogs into one directory
    while a lookup reads another. Resolution order:

    1. TIMESHEET_WORKSPACE, through `setting()` above — explicit wins.
    2. The current directory, if it already looks like a workspace (`.mcp/` or `Timesheets/`).
    3. The directory the skill is installed under, per `_install_workspace()` — which is
       where the install shapes, and the one that deliberately resolves to nothing, live.

    Returning None instead of guessing is deliberate: deriving a path from the install
    location and using it regardless is how refreshes used to report success while
    writing catalogs nowhere the reader would look.
    """
    ws = setting("TIMESHEET_WORKSPACE")
    if ws:
        return Path(ws).expanduser()
    cwd = Path.cwd()
    if _looks_like_a_workspace(cwd):
        return cwd
    return _install_workspace()
