"""Betriebsmodus einer Zone: Zeitplan, festes Preset oder Aus."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .controller import ZoneController
from .entity import ZoneEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    controller: ZoneController = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ModeSelect(controller)])


class ModeSelect(ZoneEntity, SelectEntity):
    _attr_name = "Modus"
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, controller: ZoneController) -> None:
        super().__init__(controller, "mode")

    @property
    def options(self) -> list[str]:
        return self.controller.mode_options

    @property
    def current_option(self) -> str:
        return self.controller.mode

    async def async_select_option(self, option: str) -> None:
        await self.controller.async_set_mode(option)
