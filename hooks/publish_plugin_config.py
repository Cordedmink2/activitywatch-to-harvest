"""Publish the declared plugin configuration into the session environment.

The manifest's `userConfig` block is where a user's machine and account facts are
declared, and the harness stores them for them — non-sensitive values in `settings.json`,
sensitive ones in its own credential store. It hands them back as `CLAUDE_PLUGIN_OPTION_<KEY>`
environment variables, but only to *hook* processes. The skill's scripts are run by the
model through the shell, in a process that never sees a hook's environment.

`$CLAUDE_ENV_FILE` is the bridge. On SessionStart the harness passes the path of a shell
fragment it will apply to later commands in the session; anything exported there arrives
at the scripts as an ordinary environment variable. So the values land in the layer
`skill_config` already documents as "the process environment, which is where a harness
injects values" — no new precedence, no second reader, nothing for the scripts to know
about the harness.

**How far the bridge reaches: Claude Code's Bash tool, and nothing else.** The fragment is
POSIX shell and is applied as a preamble to Bash tool calls; the PowerShell tool is given
no equivalent and loads no profile, so a script the model happens to run through
PowerShell sees none of this. That is a documented scope, not a defect here, and it is not
closed by writing a second fragment: `skills/daily/TESTING.md` § "Two ways the
configuration does not arrive" records the two mechanisms that would close it and why
neither was taken. What closes it instead is the skills directing every read of a
configured value through Bash, and `skill_config.note_for_an_unreached_shell()` naming the
shell when one gets through anyway.

The option key *is* the setting key. The harness derives the variable name by upper-casing
the declared key and replacing anything outside `[A-Za-z0-9_]` with `_`; every key this
plugin declares is already an upper-case identifier, so stripping the prefix recovers the
name the scripts ask `setting()` for, exactly. `tests/test_plugin_config.py` pins that,
because a key declared as `harvest.api-key` would round-trip to something else silently.

Nothing here *lists* the options: the set to publish is read back out of the manifest
beside this file, so the manifest stays the single declaration of the surface and the two
cannot drift. Reading it rather than trusting the `CLAUDE_PLUGIN_OPTION_` prefix is
deliberate — see `option_values()`.

**The second job this hook does: re-point the screenshot task after a plugin update.** The
`WorkScreenshots` task stores an absolute path to `screenshot_capture.py`, and under a plugin
install that path is inside the versioned cache directory this file also lives in. It is
right for the session that registered it and for no session after the next update: if the
old directory is pruned every trigger fails `0x80070002`, and if it is left in place — which
is what was observed — the task keeps running the superseded release's capture script with
`LastTaskResult 0`, looking healthy to the very check `setup` hands the user. This hook runs
at every session start from inside the *current* version, so it compares the stored path
against its own plugin root and, when they disagree, rewrites that one path and nothing
else. See `repair_screenshot_task()`; `tests/test_screenshot_task_repair.py` pins it. Issue
#29 has the design and the two alternatives it rejects.

No third-party deps — stdlib only, like every other script in this plugin.
"""
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from typing import Callable, Optional

PREFIX = "CLAUDE_PLUGIN_OPTION_"

# The one export here that is not a declared setting. It says "this process received the
# fragment", which is a different question from "anything was configured" — so it is
# written whether or not there were values to write. `skill_config` reads it to tell a
# missing setting apart from a setting that never arrived, and the spelling exists twice
# because a hook is run by path and can import nothing from the skill.
# `tests/test_plugin_config.py` pins the two together.
MARKER = "BILLABLES_CONFIG_PUBLISHED"
MANIFEST = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        os.pardir, ".claude-plugin", "plugin.json")


def declared_keys() -> set:
    """The option names this plugin declares, read from the manifest beside this file.

    Reading them rather than listing them keeps the manifest the single declaration — the
    two cannot drift. Returning an empty set on any failure means "publish nothing", which
    is the safe direction: a missing or unreadable manifest is not a reason to start
    exporting whatever else is in this process's environment.
    """
    try:
        with open(MANIFEST, encoding="utf-8") as fh:
            return set(json.load(fh).get("userConfig") or {})
    except Exception:
        return set()


def option_values(environ, declared=None) -> dict:
    """The injected options, keyed by the setting name the scripts resolve.

    Restricted to the keys this plugin declares. The prefix alone is not a safe filter:
    it is the harness's namespace, not this plugin's, so if a hook process is ever handed
    another enabled plugin's options too, filtering on the prefix would export that
    plugin's *sensitive* values into the environment of every Bash tool call for the rest
    of the session — visible to any subprocess, any `env`, anything that logs its
    environment. That the fragment reaches one tool and not the other narrows the blast
    radius and does not change the argument. Whether the harness scopes the injection was
    not something to find out from a leak, and intersecting costs one `json.load`.

    A blank value is dropped rather than published. `skill_config.has_value()` already
    treats blank as unset at every layer, and publishing `KEY=` would mean an option the
    user deliberately left empty writes an empty variable that a later reader has to know
    to ignore.
    """
    declared = declared_keys() if declared is None else declared
    out = {}
    for name, value in environ.items():
        if not name.startswith(PREFIX) or not value.strip():
            continue
        key = name[len(PREFIX):]
        if key in declared:
            out[key] = value
    return out


def render(options: dict) -> str:
    """The shell fragment exporting `options`, POSIX-quoted.

    Single quotes, with an embedded quote written as `'\\''`: the values are a user's
    tokens and paths, and a token containing `$` or a backtick must not be expanded by
    the shell that sources this. Sorted so the fragment is stable across sessions and a
    diff of it means a value actually changed.
    """
    lines = []
    for key in sorted(options):
        quoted = options[key].replace("'", "'\\''")
        lines.append(f"export {key}='{quoted}'")
    return "".join(line + "\n" for line in lines)


# --------------------------------------------------------------------------------------
# The screenshot task
# --------------------------------------------------------------------------------------

# The task `skills/daily/scripts/setup_screenshot_pipeline.ps1` registers, and where the
# capture script sits relative to the plugin root. Both are that script's facts, spelled
# again here because a hook is run by path and imports nothing from the skill.
TASK_NAME = "WorkScreenshots"
CAPTURE_SCRIPT = os.path.join("skills", "daily", "scripts", "screenshot_capture.py")
PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# How the write receives its inputs. Through the environment rather than the command line:
# the values are quoted Windows paths, and a `-Command` string would have to re-quote them
# for PowerShell, which is where a path with a space or an apostrophe would come apart.
ENV_TASK = "BILLABLES_TASK_NAME"
ENV_OLD = "BILLABLES_TASK_ARGS_OLD"
ENV_NEW = "BILLABLES_TASK_ARGS_NEW"

# The write. It compares the live action to what Python read before it changes anything:
# the read is decoded from console output in whatever code page the hook inherited, so a
# path with a non-ASCII character in it can arrive mangled, and a mismatch is a refusal
# rather than a best guess. (`-ne` is case-insensitive, which cannot produce a wrong path:
# the new string is derived from the same read.) `Set-ScheduledTask -InputObject` writes the
# whole definition back — triggers, settings, principal, state — with only the one string
# changed; observed doing exactly that on 2026-09-03, and `tests/test_screenshot_task_repair.py`
# pins it against a throwaway task. Exit codes are for the caller's outcome only; nothing prints.
WRITE_SCRIPT = (
    "$ErrorActionPreference = 'Stop'; "
    f"$t = Get-ScheduledTask -TaskName $env:{ENV_TASK}; "
    f"if ($t.Actions[0].Arguments -ne $env:{ENV_OLD}) {{ exit 3 }}; "
    f"$t.Actions[0].Arguments = $env:{ENV_NEW}; "
    "Set-ScheduledTask -InputObject $t | Out-Null"
)

_TASK_NS = "{http://schemas.microsoft.com/windows/2004/02/mit/task}"
_FIRST_ARGUMENT = re.compile(r'^\s*(?:"([^"]*)"|(\S+))')


def stored_arguments(task_xml: str) -> Optional[str]:
    """The first Exec action's `Arguments`, out of what `schtasks /Query /XML` printed.

    That tool is the read path because it does not pay a PowerShell startup, and this runs
    at every session start. Its output declares UTF-16 whatever bytes it actually printed,
    so the text is decoded first (`_decode_console`) and the declaration dropped rather
    than left to contradict it. Anything that is not a task document reads as nothing.
    """
    body = re.sub(r"^\s*<\?xml[^>]*\?>", "", task_xml, count=1)
    try:
        root = ET.fromstring(body)
    except (ET.ParseError, ValueError):
        return None
    for exec_node in root.iter(f"{_TASK_NS}Exec"):
        node = exec_node.find(f"{_TASK_NS}Arguments")
        return (node.text or "") if node is not None else ""
    return None


def _same_path(a: str, b: str) -> bool:
    return os.path.normcase(os.path.normpath(a)) == os.path.normcase(os.path.normpath(b))


def repaired_arguments(arguments: str, plugin_root: str) -> Optional[str]:
    """The stored arguments with the plugin root re-pointed at `plugin_root`, or `None`.

    `None` means leave the task alone, and it is the answer for every task this hook does
    not own: one already naming this install; one whose script does not sit at this
    plugin's `skills/daily/scripts/` layout — a hand-installed copy or the exported skill,
    both of which `setup`'s read-back check exists to catch; and one whose root is not a
    *sibling* of this one. Successive versions of one plugin install side by side under one
    parent, so a root anywhere else is most likely a checkout of this repo with the plugin
    loaded from it — observed on 2026-09-03 with a local-path marketplace, whose plugins the
    harness runs from their source folder. The rule fails safe: if the harness ever moves
    its cache the repair stops firing and `setup` catches the stale path as it does today.

    Only the root inside the first argument changes. The rest — the capture directory, the
    quoting, the order — is what the user registered, and the ticket is explicit that a
    repair rebuilding any of it is a regression.
    """
    match = _FIRST_ARGUMENT.match(arguments)
    if not match:
        return None
    script = match.group(1) if match.group(1) is not None else match.group(2)
    suffix = os.sep + CAPTURE_SCRIPT
    normalised = os.path.normpath(script)
    if not normalised.lower().endswith(suffix.lower()):
        return None
    stored_root = normalised[: -len(suffix)]
    if _same_path(stored_root, plugin_root):
        return None
    if not _same_path(os.path.dirname(stored_root), os.path.dirname(plugin_root)):
        return None
    replacement = os.path.join(plugin_root, CAPTURE_SCRIPT)
    start, end = match.span(1) if match.group(1) is not None else match.span(2)
    return arguments[:start] + replacement + arguments[end:]


def powershell_exe() -> str:
    """Windows PowerShell, which every supported Windows has, by its fixed path — not by
    `PATH`, which under Git Bash may put `pwsh` or nothing first."""
    root = os.environ.get("SystemRoot") or os.environ.get("SYSTEMROOT") or r"C:\Windows"
    return os.path.join(root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")


def _decode_console(raw: bytes) -> str:
    """Console output in whatever code page the hook inherited.

    UTF-16 when the bytes say so (a BOM, or the NULs that UTF-16 puts between ASCII
    letters — which UTF-8 would happily accept as text and then fail to parse). Otherwise
    UTF-8 first, which is what was observed, and the OEM code page when that fails, since
    OEM bytes for a non-ASCII character are rarely valid UTF-8. When every guess is wrong
    the write's own comparison refuses, so a wrong guess here costs a PowerShell start
    and never a wrong path.
    """
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff") or b"\x00" in raw[:16]:
        try:
            return raw.decode("utf-16")
        except UnicodeDecodeError:
            pass
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return raw.decode("oem")
        except (UnicodeDecodeError, LookupError):
            return raw.decode("utf-8", errors="replace")


def refusal_marker() -> str:
    """Where a refused write is remembered, outside the versioned plugin so it survives
    the session and inside the user's own profile so it needs no rights."""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP") or os.path.expanduser("~")
    return os.path.join(base, "billables", "screenshot-task-repair-refused.txt")


def _read_text(path: str) -> Optional[str]:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return None


def repair_screenshot_task(run: Callable = subprocess.run, plugin_root: Optional[str] = None,
                           windows: Optional[bool] = None, marker: Optional[str] = None) -> str:
    """Re-point a stale `WorkScreenshots` task at this plugin root.

    Returns a word naming what happened, for the tests and for anyone measuring: the read
    runs at every session start (`schtasks`, 50–100 ms observed); the write runs about once
    per release (one `powershell.exe`, ~0.5 s observed). `windows` is the *interpreter's*
    platform, not the machine's: an MSYS2 Python on Windows would build a `/c/Users/...`
    path the scheduler cannot run.

    A write that is refused is remembered against the root it was for, and not tried again
    until the root changes — i.e. until the next release. Without that, a task the user
    cannot write (one registered from an elevated shell, which `setup` documents) would
    cost a PowerShell start at every session start forever, silently, and the ticket is
    explicit that a repair which does that gets removed. `setup`'s read-back check is what
    catches the refused case, as it catches a hand install.

    Exceptions from the two subprocesses are outcomes, not failures; `main()` guards the
    rest, because the hook's one contract is that a session always starts.
    """
    if windows is None:
        windows = os.name == "nt"
    if not windows:
        return "not-windows"
    plugin_root = PLUGIN_ROOT if plugin_root is None else plugin_root
    marker = refusal_marker() if marker is None else marker
    try:
        read = run(["schtasks", "/Query", "/TN", TASK_NAME, "/XML"],
                   capture_output=True, timeout=15)
    except Exception:
        return "unreadable"
    if read.returncode != 0:
        return "no-task"
    arguments = stored_arguments(_decode_console(read.stdout or b""))
    if arguments is None:
        return "unreadable"
    repaired = repaired_arguments(arguments, plugin_root)
    if repaired is None:
        return "current"
    # Never point the task at a file that is not there: that would be the failure this
    # exists to prevent, caused by the thing meant to prevent it.
    if not os.path.isfile(os.path.join(plugin_root, CAPTURE_SCRIPT)):
        return "no-script"
    if _read_text(marker) == os.path.normcase(plugin_root):
        return "refused-earlier"
    env = dict(os.environ)
    env.update({ENV_TASK: TASK_NAME, ENV_OLD: arguments, ENV_NEW: repaired})
    try:
        write = run([powershell_exe(), "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
                     "Bypass", "-Command", WRITE_SCRIPT],
                    env=env, capture_output=True, timeout=60)
        refused = write.returncode != 0
    except Exception:
        refused = True
    try:
        if refused:
            os.makedirs(os.path.dirname(marker), exist_ok=True)
            with open(marker, "w", encoding="utf-8") as fh:
                fh.write(os.path.normcase(plugin_root))
        elif os.path.exists(marker):
            os.remove(marker)
    except OSError:
        pass
    return "write-refused" if refused else "repaired"


def main() -> int:
    env_file = os.environ.get("CLAUDE_ENV_FILE")
    if not env_file:
        # Not every hook event is given one. Nothing to publish is not a failure. (The
        # wrapper exits before starting an interpreter in this case, so the task repair
        # below is a SessionStart-only thing by the same test.)
        return 0
    # The marker first and unconditionally. A user who has configured nothing yet still
    # gets it, because what it records is that the fragment reached the reader — and the
    # message that reads it is precisely the one a user with nothing configured will see.
    # Withholding it there would make "you have not configured this" indistinguishable
    # from "your configuration did not arrive", which is the whole distinction it exists
    # to draw.
    fragment = f"export {MARKER}='1'\n" + render(option_values(os.environ))
    # Appended in one write, and appended rather than truncated: the file is shared with
    # every other hook that publishes to this session, and a partial write would leave a
    # half-quoted line that breaks every command in the session rather than one setting.
    # `newline="\n"` because this is a shell fragment, not a text document: on Windows the
    # default translation would write CRLF, and while the shell that sources it strips the
    # CR, anything that reads the file rather than sourcing it would carry a stray CR into
    # the value.
    with open(env_file, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(fragment)
    # After the publish, so a repair that fails cannot cost the configuration; and inside
    # its own guard, because the hook's one contract is that a session always starts.
    try:
        repair_screenshot_task()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
