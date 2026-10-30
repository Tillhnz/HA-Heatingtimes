"""Echte schedule.*-Entität, kompatibel mit dem HA-Schedule-Helper (und RoomMind)."""
from __future__ import annotations

from typing import Any

from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo

try:  # HA >= 2026.x
    from homeassistant.components.schedule.entity import Schedule
except ImportError:  # ältere Versionen
    from homeassistant.components.schedule import Schedule

from .const import DOMAIN
from .controller import ZoneController

_EXTRA_ATTRS = frozenset({"zone_id", "zone_name", "presets", "blocks"})


class HeatingSchedule(Schedule):
    """Wochenplan als schedule-Entität.

    State "on" während jedes Blocks (also ganztägig); die Attribute
    `temperature`, `preset` und `preset_name` zeigen den aktuellen Block.
    `schedule.get_schedule` liefert alle Blöcke inklusive Temperaturen.
    """

    _attr_has_entity_name = True

    def __init__(self, controller: ZoneController) -> None:
        self.controller = controller
        super().__init__(controller.ha_schedule_config(), editable=False)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, controller.entry_id)},
            name=controller.name,
            manufacturer="Heizplan",
            model="Heizzone",
            entry_type=DeviceEntryType.SERVICE,
        )
        unrecorded = frozenset(getattr(self, "_unrecorded_attributes", frozenset())) | _EXTRA_ATTRS
        self._unrecorded_attributes = unrecorded
        self._Entity__combined_unrecorded_attributes = (
            frozenset(getattr(self, "_entity_component_unrecorded_attributes", frozenset())) | unrecorded
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.controller.add_listener(self._handle_change))

    @callback
    def _handle_change(self) -> None:
        self.hass.async_create_task(
            self.async_update_config(self.controller.ha_schedule_config())
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = dict(super().extra_state_attributes or {})
        c = self.controller
        registry = er.async_get(self.hass)
        attrs.update(
            zone_id=c.entry_id,
            zone_name=c.name,
            presets=[
                {
                    "key": p["key"],
                    "name": p["name"],
                    "temperature": c.temps.get(p["key"]),
                    "entity_id": registry.async_get_entity_id(
                        "number", DOMAIN, f"{c.entry_id}_preset_{p['key']}"
                    ),
                }
                for p in c.presets
            ],
            blocks=c.schedule,
        )
        return attrs
