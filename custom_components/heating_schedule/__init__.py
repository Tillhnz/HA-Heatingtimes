"""Heizplan – Wochenzeitpläne für Thermostate mit einstellbaren Temperatur-Presets."""
from __future__ import annotations

import logging
from pathlib import Path

import voluptuous as vol

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .const import (
    ATTR_BLOCKS,
    ATTR_DAYS,
    CARD_FILENAME,
    DOMAIN,
    SERVICE_APPLY,
    SERVICE_SET_SCHEDULE,
    URL_BASE,
)
from .controller import ZoneController
from .schedule import DAYS, ScheduleError

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.NUMBER, Platform.SELECT, Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

ATTR_ZONE = "zone_id"

BLOCK_SCHEMA = vol.Schema(
    {vol.Required("start"): cv.string, vol.Required("preset"): cv.string}
)
SET_SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ZONE): cv.string,
        vol.Required(ATTR_DAYS): vol.All(cv.ensure_list, [vol.In(DAYS)]),
        vol.Required(ATTR_BLOCKS): vol.All(cv.ensure_list, [BLOCK_SCHEMA]),
    }
)
APPLY_SCHEMA = vol.Schema({vol.Required(ATTR_ZONE): cv.string})


def _get_controller(hass: HomeAssistant, zone: str) -> ZoneController:
    """Zone per Entry-ID oder Name finden."""
    zones: dict[str, ZoneController] = hass.data.get(DOMAIN, {})
    if zone in zones:
        return zones[zone]
    for controller in zones.values():
        if controller.name.lower() == zone.lower():
            return controller
    raise ServiceValidationError(f"Heizzone '{zone}' nicht gefunden")


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    hass.data.setdefault(DOMAIN, {})

    # Dashboard-Karte ausliefern und automatisch im Frontend laden
    integration = await async_get_integration(hass, DOMAIN)
    await hass.http.async_register_static_paths(
        [StaticPathConfig(URL_BASE, str(Path(__file__).parent / "frontend"), True)]
    )
    add_extra_js_url(hass, f"{URL_BASE}/{CARD_FILENAME}?v={integration.version}")

    async def handle_set_schedule(call: ServiceCall) -> None:
        controller = _get_controller(hass, call.data[ATTR_ZONE])
        try:
            await controller.async_set_schedule(call.data[ATTR_DAYS], call.data[ATTR_BLOCKS])
        except ScheduleError as err:
            raise ServiceValidationError(str(err)) from err

    async def handle_apply(call: ServiceCall) -> None:
        await _get_controller(hass, call.data[ATTR_ZONE]).async_apply()

    hass.services.async_register(
        DOMAIN, SERVICE_SET_SCHEDULE, handle_set_schedule, SET_SCHEDULE_SCHEMA
    )
    hass.services.async_register(DOMAIN, SERVICE_APPLY, handle_apply, APPLY_SCHEMA)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    controller = ZoneController(hass, entry)
    await controller.async_load()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = controller

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def _start(_hass: HomeAssistant) -> None:
        await controller.async_start()

    entry.async_on_unload(async_at_started(hass, _start))
    entry.async_on_unload(controller.async_stop)
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
