import os, sys
SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts")
sys.path.insert(0, SCRIPTS)
import screenshot_capture as sc

DEFAULT = os.path.join(os.path.expanduser("~"), "Pictures", "WorkScreenshots")


def test_order_monitors_left_to_right_excludes_virtual():
    # mss convention: monitors[0] is the all-screens bounding box; [1:] are real.
    monitors = [
        {"left": 0, "top": 0, "width": 6400, "height": 1440},   # [0] virtual, must drop
        {"left": 2560, "top": 0, "width": 1920, "height": 1080},
        {"left": 0, "top": 0, "width": 2560, "height": 1440},
        {"left": 4480, "top": 0, "width": 1920, "height": 1080},
    ]
    ordered = sc.order_monitors(monitors)
    assert [m["left"] for m in ordered] == [0, 2560, 4480]
    assert len(ordered) == 3


def test_order_monitors_single():
    monitors = [
        {"left": 0, "top": 0, "width": 1920, "height": 1200},
        {"left": 0, "top": 0, "width": 1920, "height": 1200},
    ]
    assert len(sc.order_monitors(monitors)) == 1


def test_capture_dir_comes_from_the_command_line_first():
    """setup_screenshot_pipeline.ps1 -ScreenshotsDir passes the directory as argv[1];
    before that it was accepted, the folder created, and then ignored."""
    assert sc.resolve_screenshots_dir([r"D:\Shots"]) == r"D:\Shots"


def test_capture_dir_falls_back_to_the_configured_setting(env_file):
    """TIMESHEET_SCREENSHOTS_DIR, resolved through `skill_config` like every other
    setting rather than a private os.environ read that skips the `.env` layer."""
    env_file.write_text("TIMESHEET_SCREENSHOTS_DIR=D:\\FromDotEnv\n", encoding="utf-8")
    assert sc.resolve_screenshots_dir([]) == r"D:\FromDotEnv"


def test_command_line_beats_the_configured_setting(env_file):
    env_file.write_text("TIMESHEET_SCREENSHOTS_DIR=D:\\FromDotEnv\n", encoding="utf-8")
    assert sc.resolve_screenshots_dir([r"D:\Shots"]) == r"D:\Shots"


def test_capture_dir_defaults_to_pictures_when_nothing_is_set():
    assert sc.resolve_screenshots_dir([]) == DEFAULT


def test_an_empty_argument_does_not_win():
    """Task Scheduler hands through an empty string when the argument is blank."""
    assert sc.resolve_screenshots_dir([""]) == DEFAULT


def test_configured_setting_falls_back_to_an_os_env_var(env_file, monkeypatch):
    monkeypatch.setenv("TIMESHEET_SCREENSHOTS_DIR", r"D:\FromOsEnv")
    assert sc.resolve_screenshots_dir([]) == r"D:\FromOsEnv"


def test_a_tilde_in_a_configured_path_is_expanded(env_file):
    """A configured value is typed by a person, and `~/Pictures/Shots` is how a person
    writes a home-relative path.

    Taken literally it names a directory called `~` under whatever the scheduled task's
    working directory happens to be — created without complaint, written to every 2.5
    minutes, and invisible to every reader, which look under the home directory. Nothing
    fails; the day simply has no screenshots on it. The default already came out absolute,
    which is why this only ever bit a user who configured one.
    """
    env_file.write_text("TIMESHEET_SCREENSHOTS_DIR=~/Pictures/Shots\n", encoding="utf-8")
    resolved = sc.resolve_screenshots_dir([])
    assert not resolved.startswith("~"), "a configured ~ reached the filesystem as a name"
    assert resolved == os.path.expanduser("~/Pictures/Shots")


def test_a_tilde_on_the_command_line_is_expanded_too(env_file):
    """The scheduled task's `-ScreenshotsDir` comes from a person the same way — the setup
    skill now tells the model to paste what `--where` resolved, and a `~` surviving one
    hop and not the other would put the writer and the readers back in different places."""
    assert sc.resolve_screenshots_dir(["~/Shots"]) == os.path.expanduser("~/Shots")


def test_take_screenshots_writes_where_it_is_told():
    """The destination is a parameter, not a module global bound from sys.argv at
    import time - importing under pytest used to bind whatever was on the command line."""
    import inspect
    assert "dest" in inspect.signature(sc.take_screenshots).parameters
