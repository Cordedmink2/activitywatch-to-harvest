import os, sys
SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts")
sys.path.insert(0, SCRIPTS)
import screenshot_capture as sc


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
