"""Gemeinsame Basis für alle Entitäten einer Heizzone."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .controller import ZoneController


class ZoneEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, controller: ZoneController, suffix: str) -> None:
        self.controller = controller
        self._attr_unique_id = f"{controller.entry_id}_{suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, controller.entry_id)},
            name=controller.name,
            manufacturer="Heizplan",
            model="Heizzone",
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.controller.add_listener(self.async_write_ha_state))
