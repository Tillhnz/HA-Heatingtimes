"""Tests der reinen Zeitplan-Logik (laufen ohne Home Assistant)."""
from datetime import datetime
import importlib.util
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

_path = Path(__file__).parents[1] / "custom_components/heating_schedule/schedule.py"
_spec = importlib.util.spec_from_file_location("schedule", _path)
s = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(s)

TZ = ZoneInfo("Europe/Berlin")
KEYS = ["komfort", "eco", "nacht", "abwesend"]


def test_parse_presets():
    assert s.parse_presets("Komfort, Eco , Büro, eco, Aus, Zeitplan, ") == [
        {"key": "komfort", "name": "Komfort"},
        {"key": "eco", "name": "Eco"},
        {"key": "buero", "name": "Büro"},
    ]


def test_normalize_sorts_merges_and_forces_midnight():
    blocks = [
        {"start": "22:00", "preset": "nacht"},
        {"start": "06:00", "preset": "komfort"},
        {"start": "07:00", "preset": "komfort"},
        {"start": "01:30", "preset": "nacht"},
    ]
    assert s.normalize_blocks(blocks, KEYS) == [
        {"start": "00:00", "preset": "nacht"},
        {"start": "06:00", "preset": "komfort"},
        {"start": "22:00", "preset": "nacht"},
    ]


def test_normalize_strict_rejects():
    with pytest.raises(s.ScheduleError):
        s.normalize_blocks([{"start": "25:00", "preset": "eco"}], KEYS)
    with pytest.raises(s.ScheduleError):
        s.normalize_blocks([{"start": "08:00", "preset": "sauna"}], KEYS)
    assert s.normalize_blocks([{"start": "08:00", "preset": "sauna"}], KEYS, strict=False) == [
        {"start": "00:00", "preset": "komfort"}
    ]


def test_preset_at_and_next_transition():
    sched = s.default_schedule(KEYS)
    fri_7 = datetime(2026, 10, 30, 7, 0, tzinfo=TZ)  # Freitag
    assert s.preset_at(sched, fri_7) == "komfort"
    assert s.next_transition(sched, fri_7) == (datetime(2026, 10, 30, 8, 30, tzinfo=TZ), "eco")


def test_transition_skips_midnight_when_preset_unchanged():
    sched = s.default_schedule(KEYS)
    fri_23 = datetime(2026, 10, 30, 23, 0, tzinfo=TZ)
    # Fr 22:30 Nacht -> Sa 00:00 Nacht (kein Wechsel) -> Sa 08:00 Komfort
    assert s.next_transition(sched, fri_23) == (datetime(2026, 10, 31, 8, 0, tzinfo=TZ), "komfort")


def test_no_transition_when_constant():
    sched = {d: [{"start": "00:00", "preset": "eco"}] for d in s.DAYS}
    assert s.next_transition(sched, datetime(2026, 10, 30, 12, 0, tzinfo=TZ)) is None
