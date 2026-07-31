"""Guards on the install/setup scripts a new user runs before anything else works.

These cover the failure modes that leave a coworker stuck or without credentials:
a script that won't parse in the shell their machine actually ships with, and an
update that deletes the `.env` they just filled in.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
INSTALL = REPO / "install"
SKILL = REPO / "skill" / "daily-timesheet"
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
def test_screenshot_setup_resolves_its_defaults_under_windows_powershell_51():
    """5.1 leaves $PSScriptRoot empty inside param(), so the -CaptureScript default blew up
    during parameter binding, before any of the script's own checks ran.

    Runs with python stripped from PATH: the script should get far enough to reach its own
    "Python not found" guard, which proves the defaults resolved — and registers no task.
    """
    script = SKILL / "scripts" / "setup_screenshot_pipeline.ps1"
    env = dict(os.environ, PATH=r"C:\Windows\System32")
    res = subprocess.run([WINPS, "-NoProfile", "-File", str(script), "-TaskName", "NeverRegistered"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    combined = res.stdout + res.stderr
    assert "Cannot bind argument" not in combined, f"parameter defaults failed to resolve:\n{combined}"
    assert "Python not found on PATH" in combined, f"unexpected failure:\n{combined}"


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

    env_file = skills / "daily-timesheet" / ".env"
    env_file.write_text("HARVEST_ACCOUNT_ID=1234567\nHARVEST_API_KEY=pat.mine\n", encoding="utf-8")

    second = subprocess.run([BASH, sh, posix(skills)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert second.returncode == 0, second.stderr
    assert env_file.is_file(), "the update deleted the user's .env"
    assert "pat.mine" in env_file.read_text(encoding="utf-8"), "the update overwrote the user's .env"
    assert (skills / "daily-timesheet" / "SKILL.md").is_file(), "skill files missing after update"


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
        assert not (skills / "daily-timesheet" / ".env").exists(), "source .env leaked into the install"
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


def test_skill_says_where_the_script_paths_resolve_from():
    """Every run's cwd is the workspace, so bare `scripts/...` paths don't resolve."""
    skill_md = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    head = skill_md.split("## Workflow", 1)[0]
    assert "skills/daily-timesheet" in head or "skills\\daily-timesheet" in head, (
        "SKILL.md never says the `scripts/` commands are relative to the skill folder"
    )
