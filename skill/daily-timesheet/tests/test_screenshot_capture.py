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
    assert sc.resolve_screenshots_dir([r"D:\Shots"], None) == r"D:\Shots"


def test_capture_dir_falls_back_to_the_configured_setting():
    """TIMESHEET_SCREENSHOTS_DIR, resolved through the same .env-first helper as
    every other setting rather than a private os.environ read."""
    assert sc.resolve_screenshots_dir([], r"D:\FromEnv") == r"D:\FromEnv"


def test_command_line_beats_the_configured_setting():
    assert sc.resolve_screenshots_dir([r"D:\Shots"], r"D:\FromEnv") == r"D:\Shots"


def test_capture_dir_defaults_to_pictures_when_nothing_is_set():
    assert sc.resolve_screenshots_dir([], None) == DEFAULT


def test_an_empty_argument_does_not_win():
    """Task Scheduler hands through an empty string when the argument is blank."""
    assert sc.resolve_screenshots_dir([""], "  ") == DEFAULT


def test_configured_setting_is_read_from_the_skill_env_file(tmp_path, monkeypatch):
    """A user who puts TIMESHEET_SCREENSHOTS_DIR in .env - the only config mechanism
    the skill documents - must not be silently ignored. Every other setting resolves
    .env first, then OS env, through harvest_client.config()."""
    import harvest_client
    env = tmp_path / ".env"
    env.write_text("TIMESHEET_SCREENSHOTS_DIR=D:\\FromDotEnv\n", encoding="utf-8")
    monkeypatch.setattr(harvest_client, "ENV_PATH", env)
    assert sc.configured_screenshots_dir() == r"D:\FromDotEnv"


def test_configured_setting_falls_back_to_an_os_env_var(tmp_path, monkeypatch):
    import harvest_client
    monkeypatch.setattr(harvest_client, "ENV_PATH", tmp_path / "absent.env")
    monkeypatch.setenv("TIMESHEET_SCREENSHOTS_DIR", r"D:\FromOsEnv")
    assert sc.configured_screenshots_dir() == r"D:\FromOsEnv"


def test_take_screenshots_writes_where_it_is_told():
    """The destination is a parameter, not a module global bound from sys.argv at
    import time - importing under pytest used to bind whatever was on the command line."""
    import inspect
    assert "dest" in inspect.signature(sc.take_screenshots).parameters
