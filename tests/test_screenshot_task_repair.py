"""The session-start hook re-points the screenshot task after a plugin update (#29).

The `WorkScreenshots` task stores an absolute path to `screenshot_capture.py`, and under a
plugin install that path is inside the *versioned* cache directory — right for the session
that registered it and wrong for every session after the next `/plugin update`. Two things
then happen, and the second is the one the health check misses: if the harness prunes the old
version directory every trigger fails `0x80070002`; if it leaves it in place — which is what
a real `claude plugin update` did on 2026-09-03, 0.0.1 and 0.0.2 side by side — the task
keeps running the superseded capture script indefinitely with `LastTaskResult 0`, which is
exactly the health check `setup` hands the user.

So the hook that already runs at every session start compares the stored path against its
own plugin root and, when they disagree, rewrites that one path and nothing else. These
tests pin the decision (which tasks are touched, which are left alone), the surgery (only
the plugin root inside the first argument changes), and the contract the hook inherits
(exit `0` whatever the machine has). The write itself is one PowerShell command; the last
test drives it against a throwaway task on a Windows machine, where `Set-ScheduledTask`
preserving the triggers can be observed rather than assumed.
"""

import os
import subprocess
import sys
import uuid

import pytest

from test_plugin_config import load_publisher

publisher = load_publisher()

SCRIPT = os.path.join("skills", "daily", "scripts", "screenshot_capture.py")
SHOTS = r"C:\Users\someone\Pictures\Work Shots"


@pytest.fixture
def roots(tmp_path):
    """Two sibling version directories the way the plugin cache lays them out, the current
    one carrying the capture script and the superseded one not needing to. Real paths,
    because the repair refuses to point a task at a script that is not there."""
    old = tmp_path / "billables" / "0.5.0"
    new = tmp_path / "billables" / "0.6.0"
    (new / "skills" / "daily" / "scripts").mkdir(parents=True)
    (new / SCRIPT).write_text("# capture", encoding="utf-8")
    old.mkdir(parents=True)
    return str(old), str(new)


def stored(root: str, shots: str = SHOTS) -> str:
    return f'"{os.path.join(root, SCRIPT)}" "{shots}"'


def task_xml(arguments: str, command: str = r"C:\Windows\pyw.exe") -> str:
    """What `schtasks /Query /XML` prints: a UTF-16 declaration over bytes that are not,
    and a blank line after every line."""
    return (
        '<?xml version="1.0" encoding="UTF-16"?>\r\n\r\n'
        '<Task version="1.3" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">\r\n\r\n'
        '  <Triggers>\r\n\r\n    <CalendarTrigger>\r\n\r\n'
        '      <StartBoundary>2026-09-03T08:30:00+12:00</StartBoundary>\r\n\r\n'
        '    </CalendarTrigger>\r\n\r\n  </Triggers>\r\n\r\n'
        '  <Actions Context="Author">\r\n\r\n    <Exec>\r\n\r\n'
        f'      <Command>{command}</Command>\r\n\r\n'
        f'      <Arguments>{arguments.replace("&", "&amp;")}</Arguments>\r\n\r\n'
        '    </Exec>\r\n\r\n  </Actions>\r\n\r\n</Task>\r\n'
    )


# --------------------------------------------------------------------------------------
# Reading the stored action
# --------------------------------------------------------------------------------------

def test_the_stored_arguments_are_read_out_of_the_native_query_output(roots):
    old, _ = roots
    assert publisher.stored_arguments(task_xml(stored(old))) == stored(old)


def test_a_task_with_no_exec_action_reads_as_nothing(roots):
    old, _ = roots
    xml = task_xml(stored(old)).replace("<Exec>", "<ComHandler>").replace("</Exec>", "</ComHandler>")
    assert publisher.stored_arguments(xml) is None


def test_output_that_is_not_a_task_reads_as_nothing():
    assert publisher.stored_arguments("ERROR: The system cannot find the file specified.") is None
    assert publisher.stored_arguments("") is None
    assert publisher.stored_arguments("\x00\x00not xml at all") is None


@pytest.mark.parametrize("encoding", ["utf-8", "cp437", "utf-16"])
def test_console_output_is_decoded_whatever_code_page_the_hook_inherited(encoding):
    """The code page is the console's, not ours: UTF-8 was observed in a pwsh console, an OEM
    page is what a plain `cmd` inherits, and UTF-16 is what the declaration claims. A
    capture directory with an accented letter must survive all three, or the write's
    comparison refuses and the task is never repaired on that machine."""
    text = task_xml(stored(r"C:\p\billables\0.5.0", r"C:\Users\Ålesund\Shots"))
    assert publisher.stored_arguments(publisher._decode_console(text.encode(encoding))) == (
        stored(r"C:\p\billables\0.5.0", r"C:\Users\Ålesund\Shots"))


# --------------------------------------------------------------------------------------
# Deciding what to rewrite
# --------------------------------------------------------------------------------------

def test_a_task_naming_the_superseded_version_is_re_pointed_at_this_one(roots):
    """The primary case from the ticket: the old directory is still there, the task still
    reports `0`, and it is running last release's capture script."""
    old, new = roots
    assert publisher.repaired_arguments(stored(old), new) == stored(new)


def test_only_the_plugin_root_inside_the_first_argument_changes(roots):
    """AC: capture directory, quoting and everything after the script path survive verbatim.
    The capture directory is the user's — a space in it is why the quotes are there — and a
    repair that re-quoted or re-ordered the arguments would be the setup script's rebuild by
    another route."""
    old, new = roots
    shots = r"C:\Users\some one\OneDrive - Firm\Shots"
    assert publisher.repaired_arguments(stored(old, shots), new) == stored(new, shots)
    # An argument list with nothing after the script, and one with more than the script
    # expects, are both carried through untouched.
    assert publisher.repaired_arguments(f'"{os.path.join(old, SCRIPT)}"', new) == (
        f'"{os.path.join(new, SCRIPT)}"')
    assert publisher.repaired_arguments(stored(old) + " --extra 1", new) == stored(new) + " --extra 1"


def test_a_task_already_naming_this_install_is_left_alone(roots):
    """The common session. Nothing to write, and nothing to start PowerShell for."""
    _, new = roots
    assert publisher.repaired_arguments(stored(new), new) is None


def test_the_comparison_is_windows_path_equality_not_string_equality(roots):
    """Case and separator differences are the same path to the scheduler."""
    _, new = roots
    assert publisher.repaired_arguments(stored(new.lower()), new) is None
    assert publisher.repaired_arguments(stored(new.replace("\\", "/")), new) is None


def test_a_hand_installed_task_is_not_ours_to_repair(roots):
    """`setup`'s read-back check is what catches a task left over from a hand install, and
    the migration guide walks the user through re-registering it deliberately. Its script
    sits at `<copy>\\scripts\\screenshot_capture.py`, not under `skills\\daily\\`, so it does
    not match the layout this plugin ships and the hook does not touch it. AC: that check
    still catches it."""
    _, new = roots
    hand = r'"C:\Users\someone\.claude\skills\daily-timesheet\scripts\screenshot_capture.py" "C:\Shots"'
    assert publisher.repaired_arguments(hand, new) is None


def test_an_exported_installs_task_is_not_ours_to_repair(roots):
    """The shared Agent Skills export lives at a stable path and is regenerated in place;
    its task never goes stale this way and must not be pointed into the plugin cache."""
    _, new = roots
    exported = r'"C:\Users\someone\.agents\skills\billables-daily\scripts\screenshot_capture.py" "C:\Shots"'
    assert publisher.repaired_arguments(exported, new) is None


def test_a_root_that_is_not_a_sibling_version_is_not_repaired(roots, tmp_path):
    """Successive versions of one plugin install side by side under one parent. A root
    anywhere else — a checkout of this repo with the plugin loaded from it, which is how the
    harness runs a local-path marketplace — would otherwise capture the user's real task on
    every session, and the next installed session would take it back."""
    old, _ = roots
    checkout = str(tmp_path / "src" / "activity-to-timesheet")
    assert publisher.repaired_arguments(stored(old), checkout) is None


def test_arguments_with_no_recognisable_script_are_left_alone(roots):
    _, new = roots
    assert publisher.repaired_arguments("", new) is None
    assert publisher.repaired_arguments('"C:\\other\\thing.py" "x"', new) is None


# --------------------------------------------------------------------------------------
# The repair, end to end against a fake scheduler
# --------------------------------------------------------------------------------------

class FakeScheduler:
    """Answers the native read and records the PowerShell write, so the decision path can
    be driven without a scheduler. `read` is what `schtasks` would print; `read_code` its
    exit status."""

    def __init__(self, read: str = "", read_code: int = 0, write_code: int = 0):
        self.read, self.read_code, self.write_code = read, read_code, write_code
        self.writes: list = []

    def __call__(self, argv, **kwargs):
        if os.path.basename(str(argv[0])).lower().startswith("schtasks"):
            return subprocess.CompletedProcess(argv, self.read_code, self.read.encode("utf-8"), b"")
        self.writes.append((argv, kwargs.get("env") or {}))
        return subprocess.CompletedProcess(argv, self.write_code, b"", b"")


def repair(fake, new, marker):
    return publisher.repair_screenshot_task(run=fake, plugin_root=new, windows=True, marker=marker)


def test_a_stale_task_is_repaired_through_one_write(roots, tmp_path):
    old, new = roots
    fake = FakeScheduler(read=task_xml(stored(old)))
    assert repair(fake, new, str(tmp_path / "marker")) == "repaired"
    assert len(fake.writes) == 1
    argv, env = fake.writes[0]
    assert "powershell" in os.path.basename(str(argv[0])).lower()
    assert env[publisher.ENV_TASK] == publisher.TASK_NAME
    assert env[publisher.ENV_OLD] == stored(old)
    assert env[publisher.ENV_NEW] == stored(new)


def test_the_write_hands_the_task_name_and_both_argument_strings_through_the_environment(roots, tmp_path):
    """Through the environment, not the command line: the values are quoted Windows paths,
    and a `-Command` string would have to re-quote them for PowerShell, which is where a
    path with a space or an apostrophe in it would come apart."""
    old, new = roots
    fake = FakeScheduler(read=task_xml(stored(old)))
    repair(fake, new, str(tmp_path / "marker"))
    argv, _ = fake.writes[0]
    assert stored(old) not in " ".join(map(str, argv))
    assert stored(new) not in " ".join(map(str, argv))


def test_a_current_task_costs_the_read_and_nothing_else(roots, tmp_path):
    _, new = roots
    fake = FakeScheduler(read=task_xml(stored(new)))
    assert repair(fake, new, str(tmp_path / "marker")) == "current"
    assert fake.writes == []


def test_a_root_without_the_capture_script_is_never_written(roots, tmp_path):
    """Pointing the task at a file that is not there would be the failure this exists to
    prevent, caused by the thing meant to prevent it — after any move of the script inside
    the plugin, every working task would break at the next update."""
    old, new = roots
    os.remove(os.path.join(new, SCRIPT))
    fake = FakeScheduler(read=task_xml(stored(old)))
    assert repair(fake, new, str(tmp_path / "marker")) == "no-script"
    assert fake.writes == []


def test_no_task_is_not_a_failure(roots, tmp_path, capsys):
    _, new = roots
    fake = FakeScheduler(read="ERROR: The system cannot find the file specified.", read_code=1)
    assert repair(fake, new, str(tmp_path / "marker")) == "no-task"
    assert fake.writes == []
    assert capsys.readouterr() == ("", "")


def test_not_windows_is_not_a_failure_and_runs_nothing(roots, tmp_path):
    """macOS and Linux ship no capture pipeline. And a POSIX Python on Windows (MSYS2's)
    would build a `/c/Users/...` path that the scheduler cannot run — so the platform
    check is on the interpreter, not on the machine."""
    old, new = roots
    fake = FakeScheduler(read=task_xml(stored(old)))
    assert publisher.repair_screenshot_task(run=fake, plugin_root=new, windows=False,
                                            marker=str(tmp_path / "marker")) == "not-windows"
    assert fake.writes == []


def test_a_machine_without_the_scheduler_tool_is_not_a_failure(roots, tmp_path):
    _, new = roots

    def missing(argv, **kwargs):
        raise FileNotFoundError(argv[0])
    assert repair(missing, new, str(tmp_path / "marker")) == "unreadable"


def test_a_refused_write_is_remembered_and_not_retried_until_the_root_changes(roots, tmp_path):
    """A task the user cannot write — registered from an elevated shell, which `setup`
    documents — must not cost a PowerShell start at every session start forever. The
    refusal is remembered against the root it was for; the next release is a new root and
    gets one fresh attempt."""
    old, new = roots
    marker = str(tmp_path / "marker")
    fake = FakeScheduler(read=task_xml(stored(old)), write_code=3)
    assert repair(fake, new, marker) == "write-refused"
    assert repair(fake, new, marker) == "refused-earlier"
    assert len(fake.writes) == 1, "the refused write was retried"

    later = os.path.join(os.path.dirname(new), "0.7.0")
    os.makedirs(os.path.join(later, os.path.dirname(SCRIPT)))
    with open(os.path.join(later, SCRIPT), "w", encoding="utf-8") as fh:
        fh.write("# capture")
    assert repair(fake, later, marker) == "write-refused"
    assert len(fake.writes) == 2, "a new release did not get its one attempt"


def test_a_successful_write_clears_an_earlier_refusal(roots, tmp_path):
    old, new = roots
    marker = str(tmp_path / "marker")
    assert repair(FakeScheduler(read=task_xml(stored(old)), write_code=3), new, marker) == "write-refused"
    assert os.path.exists(marker)
    later = os.path.join(os.path.dirname(new), "0.7.0")
    os.makedirs(os.path.join(later, os.path.dirname(SCRIPT)))
    with open(os.path.join(later, SCRIPT), "w", encoding="utf-8") as fh:
        fh.write("# capture")
    assert repair(FakeScheduler(read=task_xml(stored(old))), later, marker) == "repaired"
    assert not os.path.exists(marker)


def test_the_hook_still_exits_zero_when_the_repair_blows_up(tmp_path, monkeypatch):
    """The hook's one contract. A session must never fail to start over a scheduled task."""
    env_file = tmp_path / "sessionstart-hook-0.sh"
    monkeypatch.setenv("CLAUDE_ENV_FILE", str(env_file))

    def explode():
        raise RuntimeError("scheduler service not running")
    monkeypatch.setattr(publisher, "repair_screenshot_task", explode)
    assert publisher.main() == 0
    assert publisher.MARKER.encode() in env_file.read_bytes(), "the repair must not cost the publish"


def test_the_hook_runs_the_repair_after_publishing(tmp_path, monkeypatch):
    env_file = tmp_path / "sessionstart-hook-0.sh"
    monkeypatch.setenv("CLAUDE_ENV_FILE", str(env_file))
    calls = []
    monkeypatch.setattr(publisher, "repair_screenshot_task", lambda: calls.append("ran"))
    assert publisher.main() == 0
    assert calls == ["ran"]


# --------------------------------------------------------------------------------------
# The write, for real, against a throwaway task
# --------------------------------------------------------------------------------------

requires_task_scheduler = pytest.mark.skipif(
    sys.platform != "win32", reason="the screenshot task is a Windows scheduled task")


@requires_task_scheduler
def test_the_real_write_changes_the_path_and_keeps_everything_else(roots, tmp_path, monkeypatch):
    """AC: task name, capture directory, start time, interval, trigger days, principal,
    settings and interpreter survive; only the plugin root inside the stored path changes.

    `Set-ScheduledTask -InputObject` is documented to do this, and it was observed doing it
    on 2026-09-03 — this pins the observation. Then the refusal branch, for real: the same
    write with a stale "what was read" must exit 3 and leave the task as it is. A throwaway
    task under a unique name, disabled so it never fires, removed on the way out whatever
    happens.
    """
    old, new = roots
    name = f"BillablesRepairTest-{uuid.uuid4().hex[:8]}"
    ps = publisher.powershell_exe()
    shots = os.path.join(os.environ.get("TEMP", "C:\\Temp"), "Repair Test Shots")
    register = f"""
        $act = New-ScheduledTaskAction -Execute 'C:\\Windows\\pyw.exe' -Argument $env:ARGS
        $trg = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Tuesday,Thursday -At 09:15
        $trg.Repetition = (New-ScheduledTaskTrigger -Once -At 09:15 -RepetitionInterval (New-TimeSpan -Seconds 300) -RepetitionDuration (New-TimeSpan -Hours 8)).Repetition
        $set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -StartWhenAvailable
        Register-ScheduledTask -TaskName '{name}' -Action $act -Trigger $trg -Settings $set -Force | Out-Null
        Disable-ScheduledTask -TaskName '{name}' | Out-Null
    """
    describe = f"""
        $t = Get-ScheduledTask -TaskName '{name}'
        $r = $t.Triggers[0].Repetition
        @($t.Actions[0].Execute, $t.Actions[0].Arguments, $t.Triggers[0].StartBoundary,
          $t.Triggers[0].DaysOfWeek, $r.Interval, $r.Duration, $t.Settings.MultipleInstances,
          $t.Settings.StartWhenAvailable, $t.Principal.LogonType, $t.State) -join "`n"
    """

    def run_ps(command, **extra_env):
        return subprocess.run([ps, "-NoProfile", "-NonInteractive", "-Command", command],
                              env=dict(os.environ, **extra_env), capture_output=True, text=True)

    try:
        assert run_ps(register, ARGS=stored(old, shots)).returncode == 0
        before = run_ps(describe).stdout.splitlines()

        with monkeypatch.context() as m:
            m.setattr(publisher, "TASK_NAME", name)
            outcome = publisher.repair_screenshot_task(plugin_root=new, windows=True,
                                                       marker=str(tmp_path / "marker"))
        after = run_ps(describe).stdout.splitlines()

        refusal = run_ps(publisher.WRITE_SCRIPT, **{
            publisher.ENV_TASK: name,
            publisher.ENV_OLD: stored(old, shots),      # stale: the live task now names `new`
            publisher.ENV_NEW: stored(old, shots)})
        after_refusal = run_ps(describe).stdout.splitlines()
    finally:
        run_ps(f"Unregister-ScheduledTask -TaskName '{name}' -Confirm:$false")

    assert outcome == "repaired"
    assert after[1] == stored(new, shots), after
    assert before[0] == after[0] == r"C:\Windows\pyw.exe", "the interpreter is out of reach"
    assert before[2:] == after[2:], f"something other than the path changed:\n{before}\n{after}"
    assert after[9] == "Disabled", "the task's state was not preserved"
    assert refusal.returncode == 3, refusal.stderr
    assert after_refusal == after, "a refused write changed the task"
