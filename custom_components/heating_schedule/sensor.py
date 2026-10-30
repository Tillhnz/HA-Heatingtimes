"""Solltemperatur-Sensor – trägt außerdem alle Daten für die Dashboard-Karte."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .controller import ZoneController
from .entity import ZoneEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    controller: ZoneController = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([TargetSensor(controller)])


class TargetSensor(ZoneEntity, SensorEntity):
    _attr_name = "Solltemperatur"
    _attr_icon = "mdi:home-thermometer"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _unrecorded_attributes = frozenset({"schedule", "presets", "climate_entities"})

    def __init__(self, controller: ZoneController) -> None:
        super().__init__(controller, "target")

    @property
    def native_value(self) -> float | None:
        return self.controller.target_temperature

    def _entity_id(self, domain: str, suffix: str) -> str | None:
        return er.async_get(self.hass).async_get_entity_id(
            domain, DOMAIN, f"{self.controller.entry_id}_{suffix}"
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        c = self.controller
        nxt = c.next_change
        return {
            "zone_id": c.entry_id,
            "zone_name": c.name,
            "mode": c.mode,
            "mode_entity": self._entity_id("select", "mode"),
            "current_preset": c.current_preset,
            "next_change": nxt.isoformat() if nxt else None,
            "next_preset": c.next_preset,
            "climate_entities": c.climates,
            "presets": [
                {
                    "key": p["key"],
                    "name": p["name"],
                    "temperature": c.temps.get(p["key"]),
                    "entity_id": self._entity_id("number", f"preset_{p['key']}"),
                }
                for p in c.presets
            ],
            "schedule": c.schedule,
        }
