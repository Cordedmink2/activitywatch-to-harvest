"""Harvest's own contracts. Where a setting *comes from* is `test_config_seam.py`."""
import os, sys
import pytest

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts")
sys.path.insert(0, SCRIPTS)
from harvest_client import parse_time_to_minutes
from harvest_list import to_24h


@pytest.mark.parametrize("raw,expected", [
    ("8:15am", 8 * 60 + 15),
    ("08:15", 8 * 60 + 15),
    ("12:30pm", 12 * 60 + 30),   # noon stays 12
    ("12:30am", 30),             # midnight wraps to 0
    ("12:00am", 0),
    ("1:05pm", 13 * 60 + 5),
    ("11:59pm", 23 * 60 + 59),
    (" 9:00 AM ", 9 * 60),       # whitespace + uppercase suffix
    ("00:00", 0),
    ("23:59", 23 * 60 + 59),
])
def test_parse_valid(raw, expected):
    assert parse_time_to_minutes(raw) == expected


@pytest.mark.parametrize("raw", [
    "",            # empty
    "9am",         # no minutes
    "9.15am",      # wrong separator
    "24:00",       # hour out of range
    "10:60",       # minute out of range
    "13:00pm",     # 13pm is nonsense (would map to 25)
    "abc",
    "10:xx",
])
def test_parse_invalid_raises(raw):
    with pytest.raises(ValueError):
        parse_time_to_minutes(raw)


def test_to_24h_delegates_and_keeps_contract():
    assert to_24h("8:15am") == "08:15"
    assert to_24h("12:21pm") == "12:21"
    assert to_24h("08:15") == "08:15"
    assert to_24h(None) == "--:--"      # missing input
    assert to_24h("") == "--:--"
    assert to_24h("garbage") == "garbage"  # unparseable returns original
