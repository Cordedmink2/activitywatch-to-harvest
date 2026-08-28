"""Guards on the install/setup scripts a new user runs before anything else works.

These cover the failure modes that leave a coworker stuck or without credentials:
a script that won't parse in the shell their machine actually ships with, and an
update that deletes the `.env` they just filled in.
"""

import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
INSTALL = REPO / "install"
SKILL = REPO / "skills" / "daily"
PS_SCRIPTS = [
    INSTALL / "install_skill.ps1",
    INSTALL / "setup_workspace.ps1",
    SKILL / "scripts" / "setup_screenshot_pipeline.ps1",
]

# Windows PowerShell 5.1 is the only shell a stock Windows box has; pwsh 7 is an
# extra install. Every .ps1 has to at least parse there.
WINPS = shutil.which("powershell.exe") if sys.platform == "win32" else None
requires_winps = pytest.mark.skipif(not WINPS, reason="Windows PowerShell 5.1 not available")


def find_bash():
    """On Windows, Git Bash specifically — System32\\bash.exe is the WSL launcher,
    which mounts the drive at /mnt/c and can't open the /c/... paths used here."""
    if sys.platform != "win32":
        return shutil.which("bash")
    git = shutil.which("git")
    candidates = []
    if git:
        candidates.append(Path(git).parents[1] / "bin" / "bash.exe")
    candidates += [Path(r"C:\Program Files\Git\bin\bash.exe"),
                   Path(r"C:\Program Files (x86)\Git\bin\bash.exe")]
    for c in candidates:
        if c.is_file():
            return str(c)
    return None


BASH = find_bash()
requires_bash = pytest.mark.skipif(not BASH, reason="bash not available")


def posix(path) -> str:
    """`C:\\Users\\me` -> `/c/Users/me`, which is what Git Bash can open."""
    s = str(path).replace("\\", "/")
    if sys.platform == "win32" and len(s) > 1 and s[1] == ":":
        s = f"/{s[0].lower()}{s[2:]}"
    return s


@requires_winps
@pytest.mark.parametrize("script", PS_SCRIPTS, ids=lambda p: p.name)
def test_ps_script_parses_under_windows_powershell_51(script):
    """5.1 rejects pwsh-7-only syntax (?. / ??) and misreads UTF-8 without a BOM."""
    probe = (
        "$errs = $null; "
        f"[System.Management.Automation.Language.Parser]::ParseFile('{script}', [ref]$null, [ref]$errs) | Out-Null; "
        "if ($errs) { $errs | ForEach-Object { [Console]::Error.WriteLine($_.Message) }; exit 1 }"
    )
    res = subprocess.run([WINPS, "-NoProfile", "-Command", probe],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert res.returncode == 0, f"{script.name} fails to parse under 5.1:\n{res.stderr}"


@requires_winps
def test_setup_workspace_runs_under_windows_powershell_51(tmp_path):
    """The scaffold script must actually run on 5.1, not just parse."""
    ws = tmp_path / "ws"
    res = subprocess.run(
        [WINPS, "-NoProfile", "-File", str(INSTALL / "setup_workspace.ps1"), "-Workspace", str(ws)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert res.returncode == 0, f"exit {res.returncode}:\n{res.stdout}{res.stderr}"
    for d in ("Timesheets", "daily_exports", ".mcp"):
        assert (ws / d).is_dir(), f"{d} not created"
    assert (ws / "Timesheets" / ".context.md").is_file(), ".context.md not seeded"


@requires_winps
def test_screenshot_setup_resolves_its_defaults_under_windows_powershell_51(dry_run_setup):
    """5.1 leaves $PSScriptRoot empty inside param(), so the -CaptureScript default blew up
    during parameter binding, before any of the script's own checks ran.

    Runs with python stripped from PATH, under -DryRun: the interpreter is resolved by
    probing (the system launcher included), so a stripped PATH no longer guarantees an
    early exit — without -DryRun this test once registered a real scheduled task.
    """
    res = dry_run_setup(env=dict(os.environ, PATH=r"C:\Windows\System32"))
    combined = res.stdout + res.stderr
    assert "Cannot bind argument" not in combined, f"parameter defaults failed to resolve:\n{combined}"
    # Either outcome proves the defaults bound: the probe found a usable interpreter and
    # the dry-run report printed, or no candidate survived and the script said so.
    assert "DRYRUN Task name" in combined or "No usable Python" in combined, \
        f"unexpected failure:\n{combined}"
    assert probe_task_state() == "absent", "a stripped-PATH run registered a scheduled task"


@requires_bash
def test_sh_install_preserves_an_existing_env_file(tmp_path):
    """Re-running the installer must never delete the user's Harvest token.

    Exercises whichever copy path this machine takes (rsync when present, the
    plain-cp fallback otherwise) — both have to leave `.env` alone.
    """
    skills = tmp_path / "skills"
    sh = posix(INSTALL / "install_skill.sh")
    first = subprocess.run([BASH, sh, posix(skills)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert first.returncode == 0, first.stderr

    env_file = skills / "daily" / ".env"
    env_file.write_text("HARVEST_ACCOUNT_ID=1234567\nHARVEST_API_KEY=pat.mine\n", encoding="utf-8")

    second = subprocess.run([BASH, sh, posix(skills)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert second.returncode == 0, second.stderr
    assert env_file.is_file(), "the update deleted the user's .env"
    assert "pat.mine" in env_file.read_text(encoding="utf-8"), "the update overwrote the user's .env"
    assert (skills / "daily" / "SKILL.md").is_file(), "skill files missing after update"


@requires_bash
def test_sh_install_still_excludes_a_source_env(tmp_path):
    """A maintainer's own `.env` sitting in the clone must not ship to anyone."""
    source_env = SKILL / ".env"
    assert not source_env.exists(), "test would clobber a real .env in the working tree"
    source_env.write_text("HARVEST_API_KEY=pat.maintainer\n", encoding="utf-8")
    try:
        skills = tmp_path / "skills"
        subprocess.run([BASH, posix(INSTALL / "install_skill.sh"), posix(skills)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", check=True)
        assert not (skills / "daily" / ".env").exists(), "source .env leaked into the install"
    finally:
        os.unlink(source_env)


def test_sh_install_does_not_wipe_the_destination():
    """The fallback path used to `rm -rf "$DEST"`, taking the user's .env with it."""
    src = (INSTALL / "install_skill.sh").read_text(encoding="utf-8")
    assert 'rm -rf "$DEST"' not in src, "whole-directory wipe is back; it deletes the user's .env"


def test_readme_states_which_powershell_is_needed():
    """`pwsh` is not on a stock Windows box — prerequisites have to say so."""
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    prereqs = readme.split("## Prerequisites", 1)[1].split("\n---", 1)[0]
    assert "PowerShell 7" in prereqs and "pwsh" in prereqs, (
        "Prerequisites doesn't say which PowerShell the `pwsh -File` commands need"
    )


SCREENSHOT_SETUP = SKILL / "scripts" / "setup_screenshot_pipeline.ps1"


def test_screenshot_task_passes_the_capture_directory_to_the_script():
    """-ScreenshotsDir used to only create the folder: the capture script was launched
    with no argument and wrote to its own hardcoded default instead.

    Order matters as much as presence - the capture script has to be argv[0] and the
    directory argv[1], which is the contract resolve_screenshots_dir() reads.
    """
    src = SCREENSHOT_SETUP.read_text(encoding="utf-8-sig")
    action = [ln for ln in src.splitlines() if "New-ScheduledTaskAction" in ln]
    assert action, "no scheduled-task action found in the setup script"
    argument = action[0]
    assert "$ScreenshotsDir" in argument, (
        f"-ScreenshotsDir never reaches the capture script:\n  {argument.strip()}")
    assert argument.index("$CaptureScript") < argument.index("$ScreenshotsDir"), (
        f"capture script and directory are the wrong way round:\n  {argument.strip()}")


DRY_RUN_TASK = "DailyTimesheetDryRunProbe"


def probe_task_state():
    res = subprocess.run(
        [WINPS, "-NoProfile", "-Command",
         f"if (Get-ScheduledTask -TaskName '{DRY_RUN_TASK}' -ErrorAction SilentlyContinue) "
         "{ 'REGISTERED' } else { 'absent' }"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    return res.stdout.strip()


@pytest.fixture
def dry_run_setup():
    """Runs the screenshot setup with -DryRun under a throwaway task name: it builds the
    real scheduled-task objects and prints them, installing and registering nothing.

    Unregisters that task on the way out. Should a regression ever make -DryRun register,
    the tests below would leave the machine taking screenshots on a schedule.
    """
    def run(*args, env=None):
        return subprocess.run(
            [WINPS, "-NoProfile", "-File", str(SCREENSHOT_SETUP), "-DryRun",
             "-TaskName", DRY_RUN_TASK, *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)

    yield run
    subprocess.run(
        [WINPS, "-NoProfile", "-Command",
         f"Unregister-ScheduledTask -TaskName '{DRY_RUN_TASK}' -Confirm:$false "
         "-ErrorAction SilentlyContinue"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")


def dry_run_field(stdout, field):
    """Pull one `DRYRUN <field>: <value>` line out of the report."""
    match = re.search(rf"^DRYRUN {re.escape(field)}\s*: (.*)$", stdout, re.M)
    assert match, f"no DRYRUN {field} line in:\n{stdout}"
    return match.group(1).strip()


@requires_winps
def test_dry_run_registers_no_task(dry_run_setup, tmp_path):
    """The switch exists so the rest of these tests can inspect a real task definition
    without touching the machine's Task Scheduler."""
    res = dry_run_setup("-ScreenshotsDir", str(tmp_path / "shots"))
    assert res.returncode == 0, f"exit {res.returncode}:\n{res.stdout}{res.stderr}"
    assert probe_task_state() == "absent", "-DryRun registered a scheduled task"


@requires_winps
def test_dry_run_launches_the_capture_script_with_the_directory_after_it(dry_run_setup, tmp_path):
    """-ScreenshotsDir used to only create the folder: the capture script was launched
    with no argument and wrote to its own hardcoded default instead.

    Read off the built action rather than the source text, so the quoting that carries a
    path containing spaces is covered too.
    """
    shots = tmp_path / "shots dir with spaces"
    res = dry_run_setup("-ScreenshotsDir", str(shots))
    assert res.returncode == 0, f"exit {res.returncode}:\n{res.stdout}{res.stderr}"
    capture = SKILL / "scripts" / "screenshot_capture.py"
    assert dry_run_field(res.stdout, "Arguments") == f'"{capture}" "{shots}"'
    # pyw.exe (the version-independent launcher) is preferred over a versioned
    # pythonw.exe: the action stores an absolute path, so a Python reinstall moves
    # the versioned directory and every trigger then fails 0x80070002, silently.
    assert Path(dry_run_field(res.stdout, "Execute")).name in (
        "pyw.exe", "pythonw.exe", "python.exe"
    )


@requires_winps
def test_dry_run_repeats_across_the_requested_workday(dry_run_setup, tmp_path):
    """The repetition is grafted on from a throwaway -Once trigger; if that idiom breaks,
    the task fires once a week instead of every few minutes."""
    res = dry_run_setup("-ScreenshotsDir", str(tmp_path / "shots"),
                        "-StartTime", "09:00", "-EndTime", "17:00", "-IntervalSeconds", "300")
    assert res.returncode == 0, f"exit {res.returncode}:\n{res.stdout}{res.stderr}"
    assert dry_run_field(res.stdout, "Repetition interval") == "PT5M"
    assert dry_run_field(res.stdout, "Repetition duration") == "PT8H"
    bitmask = int(dry_run_field(res.stdout, "Days bitmask").split()[0])
    weekdays = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    assert [d for i, d in enumerate(weekdays) if bitmask & (1 << i)] == \
        ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"], "not a weekdays-only trigger"

    # Task Scheduler normalizes the boundary to UTC, so compare it back in local time.
    boundary = datetime.fromisoformat(dry_run_field(res.stdout, "Start boundary"))
    local = boundary.astimezone() if boundary.tzinfo else boundary
    assert local.strftime("%H:%M") == "09:00", f"first run is not at -StartTime: {boundary}"


@requires_winps
def test_screenshot_setup_never_selects_a_zero_byte_python_stub(dry_run_setup, tmp_path):
    """The Windows Store app-execution alias is a 0-byte python.exe that exists on PATH
    but runs nothing. Selecting on existence picks it, and the task then registers
    cleanly and never captures anything — which is how a coworker's first install died."""
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    for name in ("python.exe", "pythonw.exe", "python3.exe"):
        (stubs / name).touch()
    res = dry_run_setup(env=dict(os.environ, PATH=rf"{stubs};C:\Windows\System32"))
    if "DRYRUN Execute" in res.stdout:
        assert str(stubs) not in dry_run_field(res.stdout, "Execute"), \
            "the 0-byte stub was selected as the interpreter"
    else:
        assert res.returncode != 0 and "No usable Python" in res.stdout + res.stderr, \
            f"unexpected failure:\n{res.stdout}{res.stderr}"


@requires_winps
def test_python_exe_override_is_probed_and_used(dry_run_setup, tmp_path):
    """-PythonExe pins the interpreter (probed, then preferred over every PATH
    candidate), with the windowed sibling substituted so no console flashes."""
    res = dry_run_setup("-PythonExe", sys.executable, "-ScreenshotsDir", str(tmp_path / "shots"))
    assert res.returncode == 0, f"exit {res.returncode}:\n{res.stdout}{res.stderr}"
    exe = Path(dry_run_field(res.stdout, "Execute"))
    assert exe.parent == Path(sys.executable).parent, \
        f"-PythonExe was ignored: task runs {exe}"
    windowed = Path(sys.executable).with_name("pythonw.exe")
    if windowed.is_file():
        assert exe == windowed, f"windowed sibling not preferred: task runs {exe}"


@requires_winps
@pytest.mark.parametrize("breakage", ["zero-byte", "runs-but-fails"])
def test_python_exe_override_rejects_a_broken_interpreter(dry_run_setup, tmp_path, breakage):
    """Pointing -PythonExe at a broken install must be an error, not a silent fallback
    to whatever else is on PATH. Both observed breakages existed on disk: the 0-byte
    Store stub, and a split install that runs but can't reach its own libraries."""
    fake = tmp_path / "python.exe"
    if breakage == "zero-byte":
        fake.touch()
    else:
        # where.exe runs and exits nonzero when handed `-c "import sys,os"`.
        shutil.copy(r"C:\Windows\System32\where.exe", fake)
    res = dry_run_setup("-PythonExe", str(fake), "-ScreenshotsDir", str(tmp_path / "shots"))
    assert res.returncode != 0, f"a broken -PythonExe was accepted:\n{res.stdout}"
    assert "DRYRUN" not in res.stdout, "the script carried on past a broken -PythonExe"


@requires_winps
def test_setup_creates_the_capture_directory_before_it_would_register(dry_run_setup, tmp_path):
    """An unusable -ScreenshotsDir used to leave a registered task pointing at a
    directory that was never created, because the mkdir came after the register.

    Q: doesn't exist, so the mkdir throws; reaching the register line anyway would print
    the report. -DryRun keeps the failure case from registering a real task either way.
    """
    ok = dry_run_setup("-ScreenshotsDir", str(tmp_path / "shots"))
    assert (tmp_path / "shots").is_dir(), "the capture directory is never created"

    bad = dry_run_setup("-ScreenshotsDir", r"Q:\no-such-drive\shots")
    assert bad.returncode != 0, "an uncreatable capture directory was accepted"
    assert "DRYRUN Arguments" in ok.stdout, "the dry-run report never printed"
    assert "DRYRUN Arguments" not in bad.stdout, (
        f"registration was reached despite the directory failing:\n{bad.stdout}")


def ensure_pytest_cache():
    """pytest writes this into the skill folder as soon as the skill's own tests run,
    so a coworker's install picks it up unless the installer excludes it."""
    cache = SKILL / ".pytest_cache"
    cache.mkdir(exist_ok=True)
    (cache / "CACHEDIR.TAG").write_text(
        "Signature: 8a477f597d28d172789f06886806bc55\n", encoding="utf-8")


@pytest.fixture(scope="module", params=["sh", "ps"])
def installed(request, tmp_path_factory):
    """One real install per shell, shared by the assertions below.

    Each installer run costs about a second, so the tests inspect different parts of
    the same run rather than paying for a fresh install apiece.
    """
    shell = request.param
    if shell == "sh" and not BASH:
        pytest.skip("bash not available")
    if shell == "ps" and not WINPS:
        pytest.skip("Windows PowerShell 5.1 not available")

    ensure_pytest_cache()
    skills = tmp_path_factory.mktemp(f"skills_{shell}")
    cmd = ([BASH, posix(INSTALL / "install_skill.sh"), posix(skills)] if shell == "sh"
           else [WINPS, "-NoProfile", "-File", str(INSTALL / "install_skill.ps1"),
                 "-SkillsDir", str(skills)])
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert res.returncode == 0, f"{shell} installer exited {res.returncode}:\n{res.stdout}{res.stderr}"
    return res, skills / "daily"


def test_install_copies_the_skill(installed):
    _, dest = installed
    assert (dest / "SKILL.md").is_file(), "skill files missing after install"


def test_install_excludes_pytest_cache(installed):
    _, dest = installed
    assert not (dest / ".pytest_cache").exists(), "pytest scratch data shipped into the install"


def test_install_reports_the_version_it_installed(installed):
    res, _ = installed
    assert latest_changelog_version() in res.stdout, \
        f"installer never says which version it installed:\n{res.stdout}"


def latest_changelog_version() -> str:
    changelog = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(r"^## \[(\d+\.\d+\.\d+)\]", changelog, re.M)
    assert match, "no released version heading in CHANGELOG.md"
    return match.group(1)


def test_installed_skill_carries_a_version_marker():
    """Without one there's no way to tell an installed copy's version from a stale one."""
    marker = SKILL / "VERSION"
    assert marker.is_file(), "the skill ships no VERSION file"
    assert re.fullmatch(r"\d+\.\d+\.\d+", marker.read_text(encoding="utf-8").strip()), \
        "VERSION is not a bare semver string"


def test_version_marker_matches_the_changelog():
    """A marker that drifts from the changelog is worse than none."""
    version = (SKILL / "VERSION").read_text(encoding="utf-8").strip()
    assert version == latest_changelog_version()


@pytest.mark.parametrize("script", ["install/install_skill.sh", "install/setup_workspace.sh"])
def test_shell_scripts_check_out_with_lf_endings(script):
    """Windows defaults to core.autocrlf=true, so a fresh clone rewrites these to CRLF
    and bash dies on the shebang's trailing \\r before running a line."""
    res = subprocess.run(["git", "check-attr", "eol", "--", script],
                         cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == f"{script}: eol: lf", (
        f"no .gitattributes rule forcing LF for {script}: {res.stdout.strip()}"
    )


def test_skill_says_where_the_script_paths_resolve_from():
    """Every run's cwd is the workspace, so bare `scripts/...` paths don't resolve.

    What the instruction may not do is name a directory. It used to spell out
    `$HOME/.claude/skills/daily-timesheet/scripts/...`, which is one install shape out of
    several — a plugin, a shared Agent Skills directory, a harness's own skills folder —
    and a wrong prefix fails as "script not found", reading like a broken skill.
    """
    skill_md = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    head = skill_md.split("## Workflow", 1)[0]
    assert "this skill's own folder" in head, (
        "SKILL.md never says the `scripts/` commands are relative to the skill folder"
    )
    # The instruction is only usable if it also says *how* to get that folder. Matched as
    # the whole phrase, because "SKILL.md" and "read" each occur incidentally all over the
    # head — a substring pair would pass with the instruction deleted.
    assert re.search(r"the directory this `SKILL\.md` was read from", head), (
        "SKILL.md never says to resolve that folder from where this file was read, so the "
        "model has nothing to build the prefix out of"
    )


INSTRUCTIONS = [SKILL / "SKILL.md", *sorted((SKILL / "references").glob("*.md"))]


@pytest.mark.parametrize("doc", INSTRUCTIONS, ids=lambda p: p.name)
def test_no_shipped_instruction_hardcodes_a_harness_skills_directory(doc):
    """A path into one harness's skills directory is wrong for every other install.

    The skill ships as a plugin, is exported into the shared Agent Skills directory, and
    can still be copied in by hand — so its own location is something to resolve at run
    time, never something to write down. Describing the *shapes* is fine and belongs in
    `scripts/skill_config.py`; an instruction the model will paste into a command is not.
    """
    text = doc.read_text(encoding="utf-8")
    offenders = [line.strip() for line in text.splitlines()
                 if ".claude/skills" in line or ".claude\\skills" in line]
    assert not offenders, (
        f"{doc.name} hardcodes a harness-specific skills path:\n  " + "\n  ".join(offenders))
