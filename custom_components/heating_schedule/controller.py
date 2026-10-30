"""Daten einer Heizzone: Presets, Temperaturen und Wochenplan."""
from __future__ import annotations

from collections.abc import Callable
import copy
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.storage import Store

from .const import CONF_PRESETS, DEFAULT_PRESET_NAMES, DEFAULT_TEMP, DEFAULT_TEMPS, DOMAIN, STORAGE_VERSION
from .schedule import DAYS, default_schedule, normalize_blocks, parse_presets, to_ha_schedule


class ZoneController:
    """Hält Presets, Temperaturen und Zeitplan einer Zone und speichert sie."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry_id = entry.entry_id
        conf = {**entry.data, **entry.options}
        self.name: str = conf.get(CONF_NAME) or entry.title
        self.presets = parse_presets(conf.get(CONF_PRESETS)) or parse_presets(DEFAULT_PRESET_NAMES)
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self.temps: dict[str, float] = {}
        self.schedule: dict[str, list[dict[str, str]]] = {}
        self._listeners: list[CALLBACK_TYPE] = []

    @property
    def preset_keys(self) -> list[str]:
        return [p["key"] for p in self.presets]

    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        keys = self.preset_keys
        stored = data.get("temps", {})
        self.temps = {k: float(stored.get(k, DEFAULT_TEMPS.get(k, DEFAULT_TEMP))) for k in keys}
        fallback = default_schedule(keys)
        raw = data.get("schedule") or fallback
        self.schedule = {
            day: normalize_blocks(raw.get(day) or fallback[day], keys, strict=False) for day in DAYS
        }

    def ha_schedule_config(self) -> dict[str, Any]:
        """Konfiguration im Format des HA-Schedule-Helpers (mit Temperatur je Block)."""
        return {
            "id": f"{self.entry_id}_schedule",
            "name": "Zeitplan",
            "icon": "mdi:radiator",
            **to_ha_schedule(self.schedule, self.presets, self.temps),
        }

    @callback
    def _save(self) -> None:
        self._store.async_delay_save(lambda: {"temps": self.temps, "schedule": self.schedule}, 1)

    @callback
    def add_listener(self, update: CALLBACK_TYPE) -> Callable[[], None]:
        self._listeners.append(update)

        @callback
        def remove() -> None:
            self._listeners.remove(update)

        return remove

    @callback
    def _changed(self) -> None:
        self._save()
        for update in list(self._listeners):
            update()

    @callback
    def set_temp(self, key: str, value: float) -> None:
        self.temps[key] = round(float(value), 1)
        self._changed()

    @callback
    def set_schedule(self, days: list[str], blocks: list[dict[str, Any]]) -> None:
        normalized = normalize_blocks(blocks, self.preset_keys, strict=True)
        for day in days:
            self.schedule[day] = copy.deepcopy(normalized)
        self._changed()
