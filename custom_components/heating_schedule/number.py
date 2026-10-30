"""Temperatur-Presets als einstellbare Variablen (number-Entitäten)."""
from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, MAX_TEMP, MIN_TEMP, TEMP_STEP
from .controller import ZoneController
from .entity import ZoneEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    controller: ZoneController = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(PresetTemperature(controller, p) for p in controller.presets)


class PresetTemperature(ZoneEntity, NumberEntity):
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_min_value = MIN_TEMP
    _attr_native_max_value = MAX_TEMP
    _attr_native_step = TEMP_STEP
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:thermometer"

    def __init__(self, controller: ZoneController, preset: dict[str, str]) -> None:
        super().__init__(controller, f"preset_{preset['key']}")
        self._key = preset["key"]
        self._attr_name = f"Temperatur {preset['name']}"

    @property
    def native_value(self) -> float | None:
        return self.controller.temps.get(self._key)

    async def async_set_native_value(self, value: float) -> None:
        await self.controller.async_set_temp(self._key, value)
