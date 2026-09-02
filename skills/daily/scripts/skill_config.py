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

# The two variables the note below is decided from.
#
# `CLAUDECODE` is set by Claude Code in every tool process, in both shells, so its absence
# means an ordinary terminal: nothing was published there for any shell to have missed.
#
# `PUBLISHED_MARK` is the one export the publishing hook makes that is not a declared
# setting. It travels *in the same fragment as the values*, which is the whole point: its
# absence means this process did not receive that fragment, and nothing can separate the
# two, because there is no route by which the values arrive without it. The first version
# of this check asked whether Git Bash's own `MSYSTEM` was set, as a proxy for the same
# question, and was wrong — `MSYSTEM` is inherited from whatever launched Claude Code, so
# on a machine where the session was started from a Git Bash terminal the PowerShell tool
# carries it too and the check was silenced for exactly the user it was written for.
# `TESTING.md` § "Two ways the configuration does not arrive" holds the record.
#
# The hook cannot import this module — it is run by path, from a directory with no
# relationship to the skill — so the spelling exists twice. `tests/test_plugin_config.py`
# pins the two together; a mismatch would silently make every session look unpublished.
IN_A_SESSION = "CLAUDECODE"
PUBLISHED_MARK = "BILLABLES_CONFIG_PUBLISHED"

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
    """The extra cause a missing-setting message carries when the published configuration
    did not reach this process at all. An empty string when it did, or could not have.

    A plugin install's values are published by a SessionStart hook writing a POSIX shell
    fragment, and Claude Code applies that to its **Bash** tool alone — the PowerShell tool
    is given no equivalent and loads no profile. So a script the model happens to run
    through PowerShell reports the timezone or the credentials missing on a machine that
    is configured perfectly well, and the two lines above this note send the user off to
    start a new session or install Git Bash. Neither is the fix, and following either
    costs them the run. `TESTING.md` § "Two ways the configuration does not arrive"
    carries the evidence and the mechanisms rejected before settling on saying so.

    **What is checked is the fact itself, not a proxy for it.** The marker rides in the
    same fragment as the values, so a process holding one holds the other; there is no
    arrangement of shells, launchers or inherited environments that delivers the values
    without it. That is what the first version got wrong — see `PUBLISHED_MARK` above.

    It stays silent unless this is a **plugin** install, because that is the only shape
    with a publishing step to have missed. An exported or hand-installed copy reads its
    values from `.env`, and telling that user to change shell would name a mechanism that
    is not in play and a fix that does nothing.

    Three causes remain and nothing here can separate them — the fragment is equally
    absent when the hook never started, and when this plugin is not enabled in the
    directory the session began in — so all three are named, which costs the user two
    lines and saves them a reinstall. The enablement one is the least guessable of the
    three: a plugin installed at **local** scope is bound to the one directory it was
    installed from (`installed_plugins.json` records it as a `projectPath`), so a sibling
    checkout gets no hook, no fragment and no values in *either* shell — while the two
    fixes the note used to offer, re-run in Bash and install Git Bash, are both already
    satisfied. `claude plugin list` is the only thing that tells them apart, so the note
    names the check and not a fix.

    A shell can only be the cause where there are two of them, so that cause is dropped
    on a platform with no PowerShell tool; the other two are not platform-specific and
    are named everywhere.

    `platform` and `environ` are parameters so the cells are driven by argument; the
    install shape is read from `SKILL_ROOT`, which the tests relocate anyway.
    """
    platform = sys.platform if platform is None else platform
    environ = os.environ if environ is None else environ
    if not _is_a_plugin_install():
        return ""
    if not environ.get(IN_A_SESSION) or environ.get(PUBLISHED_MARK):
        return ""
    if platform != "win32":
        return (
            "\n  The configuration was not published to this session: the SessionStart\n"
            "  hook that publishes it did not run. Starting a new session will not\n"
            "  change that. Two causes:\n"
            "  - this plugin may not be enabled in the directory this session started\n"
            "    from. An install made at local scope is bound to the one directory it\n"
            "    was installed from, and no hook runs anywhere else. Run\n"
            "    `claude plugin list` to see whether it is enabled here.\n"
            "  - or the hook could not start — see references/setup.md § 'When the\n"
            "    configuration does not arrive'.")
    return (
        "\n  The configuration was not published to this command, so starting a new\n"
        "  session will not help. Three causes, and the first is the common one:\n"
        "  - the command did not come from the **Bash** tool. The values are published\n"
        "    as a POSIX shell fragment, which Claude Code applies to Bash tool calls and\n"
        "    to nothing else, so PowerShell reports them missing however well this\n"
        "    machine is configured. Re-run this same command through the Bash tool.\n"
        "  - or this plugin is not enabled in the directory this session started from. An\n"
        "    install made at local scope is bound to the one directory it was installed\n"
        "    from; anywhere else the plugin is disabled, no SessionStart hook runs, and\n"
        "    nothing is published to any shell. Run `claude plugin list` to see whether it\n"
        "    is enabled here.\n"
        "  - or the publishing hook could not start, which on Windows means Git Bash is\n"
        "    not installed. references/setup.md § 'When the configuration does not\n"
        "    arrive' has that one.")


def _looks_like_a_workspace(candidate: Path) -> bool:
    return (candidate / ".mcp").is_dir() or (candidate / "Timesheets").is_dir()


def _is_a_plugin_root(candidate: Path) -> bool:
    """`.claude-plugin/` is the harness's own marker for a plugin root; the manifest
    inside it is what declares the configuration surface. One copy of that fact, because
    the two callers below want it for opposite reasons."""
    return (candidate / ".claude-plugin").is_dir()


def _is_a_plugin_install() -> bool:
    """Whether this skill is running from inside a plugin — `<plugin>/skills/<name>`.

    `note_for_an_unreached_shell()` asks, so that it speaks only where there is a
    publishing step to have missed. Every other install shape reads its values from
    `.env` and has no session hook in the picture at all; telling that user to change
    shell would name a mechanism that is not in play and a fix that does nothing.

    Anchored on the shape rather than a depth, for the reasons `_install_workspace()`
    sets out below.
    """
    parent = SKILL_ROOT.parent
    return parent.name == "skills" and _is_a_plugin_root(parent.parent)


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
    if _is_a_plugin_root(root):
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
