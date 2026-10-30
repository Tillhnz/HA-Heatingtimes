"""Reine Zeitplan-Logik (ohne Home-Assistant-Abhängigkeiten, damit testbar)."""
from __future__ import annotations

from datetime import datetime, time, timedelta
import re
import unicodedata
from typing import Any, Iterable

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
RESERVED = {"zeitplan", "aus"}


class ScheduleError(ValueError):
    """Ungültige Zeitplan-Daten."""


def slugify(text: str) -> str:
    """Einfacher Slug: 'Komfort Plus' -> 'komfort_plus', 'Büro' -> 'buero'."""
    text = text.strip().lower()
    for src, dst in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(src, dst)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def parse_presets(raw: str | Iterable[str] | None) -> list[dict[str, str]]:
    """Wandelt 'Komfort, Eco, Nacht' in [{key, name}, ...] um."""
    if raw is None:
        return []
    names = raw.split(",") if isinstance(raw, str) else list(raw)
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for name in names:
        name = str(name).strip()
        key = slugify(name)
        if not key or key in seen or name.lower() in RESERVED:
            continue
        seen.add(key)
        result.append({"key": key, "name": name})
    return result


def parse_time(value: str) -> int:
    """'HH:MM' oder 'HH:MM:SS' -> Minuten seit Mitternacht."""
    match = re.fullmatch(r"\s*(\d{1,2}):(\d{2})(?::\d{2})?\s*", str(value))
    if not match:
        raise ScheduleError(f"Ungültige Uhrzeit: {value!r}")
    hours, minutes = int(match.group(1)), int(match.group(2))
    if hours > 23 or minutes > 59:
        raise ScheduleError(f"Ungültige Uhrzeit: {value!r}")
    return hours * 60 + minutes


def fmt_time(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def normalize_blocks(
    blocks: Iterable[dict[str, Any]],
    preset_keys: list[str],
    *,
    strict: bool = True,
) -> list[dict[str, str]]:
    """Sortiert, entdoppelt und prüft Blöcke. Der erste Block beginnt immer um 00:00.

    strict=False ersetzt unbekannte Presets/Zeiten still (für gespeicherte Altdaten).
    """
    if not preset_keys:
        raise ScheduleError("Keine Temperatur-Presets definiert")
    by_start: dict[int, str] = {}
    for block in blocks or []:
        try:
            start = parse_time(block["start"])
            preset = str(block["preset"])
        except (KeyError, TypeError, ScheduleError) as err:
            if strict:
                raise ScheduleError(f"Ungültiger Block: {block!r}") from err
            continue
        if preset not in preset_keys:
            if strict:
                raise ScheduleError(f"Unbekanntes Preset: {preset!r}")
            preset = preset_keys[0]
        by_start[start] = preset

    if not by_start:
        return [{"start": "00:00", "preset": preset_keys[0]}]

    ordered = sorted(by_start.items())
    if ordered[0][0] != 0:
        ordered[0] = (0, ordered[0][1])

    # Aufeinanderfolgende gleiche Presets zusammenführen
    merged: list[tuple[int, str]] = []
    for start, preset in ordered:
        if merged and merged[-1][1] == preset:
            continue
        merged.append((start, preset))
    return [{"start": fmt_time(s), "preset": p} for s, p in merged]


def default_schedule(preset_keys: list[str]) -> dict[str, list[dict[str, str]]]:
    comfort = preset_keys[0]
    eco = preset_keys[1] if len(preset_keys) > 1 else comfort
    night = preset_keys[2] if len(preset_keys) > 2 else preset_keys[-1]
    workday = [
        {"start": "00:00", "preset": night},
        {"start": "06:00", "preset": comfort},
        {"start": "08:30", "preset": eco},
        {"start": "17:00", "preset": comfort},
        {"start": "22:30", "preset": night},
    ]
    weekend = [
        {"start": "00:00", "preset": night},
        {"start": "08:00", "preset": comfort},
        {"start": "23:00", "preset": night},
    ]
    return {
        day: normalize_blocks(weekend if day in ("sat", "sun") else workday, preset_keys)
        for day in DAYS
    }


def preset_at(schedule: dict[str, list[dict[str, str]]], when: datetime) -> str:
    """Preset, das zum Zeitpunkt `when` aktiv ist."""
    blocks = schedule[DAYS[when.weekday()]]
    minute = when.hour * 60 + when.minute
    active = blocks[0]["preset"]
    for block in blocks:
        if parse_time(block["start"]) <= minute:
            active = block["preset"]
        else:
            break
    return active


def next_transition(
    schedule: dict[str, list[dict[str, str]]], when: datetime
) -> tuple[datetime, str] | None:
    """Nächster Zeitpunkt, an dem sich das Preset ändert (über Tagesgrenzen hinweg)."""
    current = preset_at(schedule, when)
    for offset in range(8):
        date = when.date() + timedelta(days=offset)
        for block in schedule[DAYS[date.weekday()]]:
            minutes = parse_time(block["start"])
            start = datetime.combine(
                date, time(minutes // 60, minutes % 60), tzinfo=when.tzinfo
            )
            if start <= when or block["preset"] == current:
                continue
            return start, block["preset"]
    return None
