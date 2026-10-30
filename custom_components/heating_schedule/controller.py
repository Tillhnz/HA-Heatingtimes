"""Steuerlogik einer Heizzone: Zeitplan auswerten und Thermostate setzen."""
from __future__ import annotations

from collections.abc import Callable
import copy
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import (
    async_track_point_in_time,
    async_track_state_change_event,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    CONF_CLIMATES,
    CONF_PRESETS,
    DEFAULT_PRESET_NAMES,
    DEFAULT_TEMP,
    DEFAULT_TEMPS,
    DOMAIN,
    MAX_TEMP,
    MIN_TEMP,
    OPTION_OFF,
    OPTION_SCHEDULE,
    STORAGE_VERSION,
)
from .schedule import (
    DAYS,
    default_schedule,
    next_transition,
    normalize_blocks,
    parse_presets,
    preset_at,
)

_LOGGER = logging.getLogger(__name__)
_BAD_STATES = (STATE_UNAVAILABLE, STATE_UNKNOWN)


class ZoneController:
    """Hält Presets, Zeitplan und Modus einer Zone und steuert die Thermostate."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry_id = entry.entry_id
        conf = {**entry.data, **entry.options}
        self.name: str = conf.get(CONF_NAME) or entry.title
        self.climates: list[str] = list(conf.get(CONF_CLIMATES, []))
        self.presets = parse_presets(conf.get(CONF_PRESETS)) or parse_presets(
            DEFAULT_PRESET_NAMES
        )
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self.temps: dict[str, float] = {}
        self.schedule: dict[str, list[dict[str, str]]] = {}
        self.mode: str = OPTION_SCHEDULE
        self.next_change = None
        self.next_preset: str | None = None
        self._listeners: list[CALLBACK_TYPE] = []
        self._unsub_timer: CALLBACK_TYPE | None = None
        self._unsub_states: CALLBACK_TYPE | None = None
        self._started = False

    # ------------------------------------------------------------------ Daten
    @property
    def preset_keys(self) -> list[str]:
        return [p["key"] for p in self.presets]

    def preset_name(self, key: str | None) -> str | None:
        return next((p["name"] for p in self.presets if p["key"] == key), None)

    @property
    def mode_options(self) -> list[str]:
        return [OPTION_SCHEDULE, *(p["name"] for p in self.presets), OPTION_OFF]

    @property
    def current_preset(self) -> str | None:
        """Aktives Preset (None = Heizung aus)."""
        if self.mode == OPTION_OFF:
            return None
        if self.mode == OPTION_SCHEDULE:
            return preset_at(self.schedule, dt_util.now())
        return next(
            (p["key"] for p in self.presets if p["name"] == self.mode),
            self.preset_keys[0],
        )

    @property
    def target_temperature(self) -> float | None:
        preset = self.current_preset
        return None if preset is None else self.temps.get(preset)

    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        keys = self.preset_keys
        stored_temps = data.get("temps", {})
        self.temps = {
            key: float(stored_temps.get(key, DEFAULT_TEMPS.get(key, DEFAULT_TEMP)))
            for key in keys
        }
        raw = data.get("schedule") or default_schedule(keys)
        fallback = default_schedule(keys)
        self.schedule = {
            day: normalize_blocks(raw.get(day) or fallback[day], keys, strict=False)
            for day in DAYS
        }
        mode = data.get("mode", OPTION_SCHEDULE)
        self.mode = mode if mode in self.mode_options else OPTION_SCHEDULE

    @callback
    def _save(self) -> None:
        self._store.async_delay_save(
            lambda: {"temps": self.temps, "schedule": self.schedule, "mode": self.mode},
            1,
        )

    # -------------------------------------------------------------- Listener
    @callback
    def add_listener(self, update: CALLBACK_TYPE) -> Callable[[], None]:
        self._listeners.append(update)

        @callback
        def remove() -> None:
            self._listeners.remove(update)

        return remove

    @callback
    def _notify(self) -> None:
        for update in list(self._listeners):
            update()

    # ------------------------------------------------------------ Änderungen
    async def async_set_temp(self, key: str, value: float) -> None:
        self.temps[key] = round(float(value), 1)
        self._save()
        if key == self.current_preset:
            await self.async_apply()
        else:
            self._notify()

    async def async_set_mode(self, option: str) -> None:
        if option not in self.mode_options:
            raise HomeAssistantError(f"Unbekannter Modus: {option}")
        self.mode = option
        self._save()
        await self.async_apply()

    async def async_set_schedule(
        self, days: list[str], blocks: list[dict[str, Any]]
    ) -> None:
        normalized = normalize_blocks(blocks, self.preset_keys, strict=True)
        for day in days:
            self.schedule[day] = copy.deepcopy(normalized)
        self._save()
        await self.async_apply()

    # -------------------------------------------------------------- Ablauf
    async def async_start(self) -> None:
        self._started = True
        if self.climates:
            self._unsub_states = async_track_state_change_event(
                self.hass, self.climates, self._handle_climate_change
            )
        await self.async_apply()

    @callback
    def async_stop(self) -> None:
        self._started = False
        for unsub in (self._unsub_timer, self._unsub_states):
            if unsub:
                unsub()
        self._unsub_timer = self._unsub_states = None

    async def async_apply(self) -> None:
        """Zeitplan neu planen und Solltemperatur an alle Thermostate senden."""
        self._schedule_next()
        if self._started:
            for entity_id in self.climates:
                await self._push(entity_id)
        self._notify()

    @callback
    def _schedule_next(self) -> None:
        if self._unsub_timer:
            self._unsub_timer()
            self._unsub_timer = None
        self.next_change, self.next_preset = None, None
        if self.mode != OPTION_SCHEDULE:
            return
        transition = next_transition(self.schedule, dt_util.now())
        if transition is None:
            return
        self.next_change, self.next_preset = transition
        self._unsub_timer = async_track_point_in_time(
            self.hass, self._handle_timer, self.next_change
        )

    @callback
    def _handle_timer(self, _now) -> None:
        self._unsub_timer = None
        self.hass.async_create_task(self.async_apply())

    @callback
    def _handle_climate_change(self, event: Event) -> None:
        """Thermostat kommt (wieder) online -> aktuelle Solltemperatur nachschieben."""
        old, new = event.data.get("old_state"), event.data.get("new_state")
        if new is None or new.state in _BAD_STATES:
            return
        if old is None or old.state in _BAD_STATES:
            self.hass.async_create_task(self._push(new.entity_id))

    async def _push(self, entity_id: str) -> None:
        state = self.hass.states.get(entity_id)
        if state is None or state.state in _BAD_STATES:
            return
        hvac_modes = state.attributes.get("hvac_modes") or []
        temp = self.target_temperature
        try:
            if temp is None:
                if state.state != "off" and "off" in hvac_modes:
                    await self.hass.services.async_call(
                        "climate",
                        "set_hvac_mode",
                        {"entity_id": entity_id, "hvac_mode": "off"},
                        blocking=True,
                    )
                return
            low = state.attributes.get("min_temp", MIN_TEMP)
            high = state.attributes.get("max_temp", MAX_TEMP)
            data: dict[str, Any] = {
                "entity_id": entity_id,
                "temperature": min(max(temp, low), high),
            }
            if state.state == "off" and "heat" in hvac_modes:
                data["hvac_mode"] = "heat"
            await self.hass.services.async_call(
                "climate", "set_temperature", data, blocking=True
            )
        except HomeAssistantError as err:
            _LOGGER.warning("%s: konnte %s nicht setzen: %s", self.name, entity_id, err)
