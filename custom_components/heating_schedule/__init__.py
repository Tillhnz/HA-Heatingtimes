"""Heizplan – Wochenzeitplan als schedule-Entität mit einstellbaren Temperatur-Presets."""
from __future__ import annotations

from datetime import timedelta
import logging
from pathlib import Path

try:  # HA >= 2026.12 nutzt probatio statt voluptuous
    import probatio as vol
except ImportError:
    import voluptuous as vol

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import EntityPlatform
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .const import ATTR_BLOCKS, ATTR_DAYS, ATTR_ZONE, CARD_FILENAME, DOMAIN, SERVICE_SET_SCHEDULE, URL_BASE
from .controller import ZoneController
from .schedule import DAYS, ScheduleError
from .schedule_entity import HeatingSchedule

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.NUMBER]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SET_SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ZONE): cv.string,
        vol.Required(ATTR_DAYS): vol.All(cv.ensure_list, [vol.In(DAYS)]),
        vol.Required(ATTR_BLOCKS): vol.All(
            cv.ensure_list,
            [vol.Schema({vol.Required("start"): cv.string, vol.Required("preset"): cv.string})],
        ),
    }
)


def _get_controller(hass: HomeAssistant, zone: str) -> ZoneController:
    """Zone per Entry-ID, Name oder schedule-Entität finden."""
    zones: dict[str, ZoneController] = hass.data.get(DOMAIN, {})
    if zone in zones:
        return zones[zone]
    for controller in zones.values():
        if controller.name.lower() == zone.lower():
            return controller
    if zone.startswith("schedule.") and (state := hass.states.get(zone)):
        if (zid := state.attributes.get("zone_id")) in zones:
            return zones[zid]
    raise ServiceValidationError(f"Heizzone '{zone}' nicht gefunden")


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    hass.data.setdefault(DOMAIN, {})

    integration = await async_get_integration(hass, DOMAIN)
    await hass.http.async_register_static_paths(
        [StaticPathConfig(URL_BASE, str(Path(__file__).parent / "frontend"), True)]
    )
    add_extra_js_url(hass, f"{URL_BASE}/{CARD_FILENAME}?v={integration.version}")

    async def handle_set_schedule(call: ServiceCall) -> None:
        controller = _get_controller(hass, call.data[ATTR_ZONE])
        try:
            controller.set_schedule(call.data[ATTR_DAYS], call.data[ATTR_BLOCKS])
        except ScheduleError as err:
            raise ServiceValidationError(str(err)) from err

    hass.services.async_register(DOMAIN, SERVICE_SET_SCHEDULE, handle_set_schedule, SET_SCHEDULE_SCHEMA)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    controller = ZoneController(hass, entry)
    await controller.async_load()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = controller

    # Die Zeitplan-Entität gehört in die Domain "schedule", damit sie überall wie ein
    # normaler Zeitplan-Helfer funktioniert (Auswahllisten, schedule.get_schedule, RoomMind).
    platform = EntityPlatform(
        hass=hass,
        logger=_LOGGER,
        domain="schedule",
        platform_name=DOMAIN,
        platform=None,
        scan_interval=timedelta(seconds=30),
        entity_namespace=None,
    )
    platform.config_entry = entry
    await platform.async_add_entities([HeatingSchedule(controller)])
    entry.async_on_unload(platform.async_reset)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Gespeicherten Zeitplan löschen, wenn die Zone entfernt wird."""
    from homeassistant.helpers.storage import Store

    await Store(hass, 1, f"{DOMAIN}.{entry.entry_id}").async_remove()
