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
    assert sc.resolve_screenshots_dir([r"D:\Shots"], {}) == r"D:\Shots"


def test_capture_dir_falls_back_to_the_environment():
    assert sc.resolve_screenshots_dir([], {"TIMESHEET_SCREENSHOTS_DIR": r"D:\FromEnv"}) == r"D:\FromEnv"


def test_command_line_beats_the_environment():
    got = sc.resolve_screenshots_dir([r"D:\Shots"], {"TIMESHEET_SCREENSHOTS_DIR": r"D:\FromEnv"})
    assert got == r"D:\Shots"


def test_capture_dir_defaults_to_pictures_when_nothing_is_set():
    assert sc.resolve_screenshots_dir([], {}) == DEFAULT


def test_an_empty_argument_does_not_win():
    """Task Scheduler hands through an empty string when the argument is blank."""
    assert sc.resolve_screenshots_dir([""], {}) == DEFAULT
