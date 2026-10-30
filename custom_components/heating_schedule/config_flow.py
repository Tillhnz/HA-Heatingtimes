"""Einrichtung einer Heizzone über die Oberfläche."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    TextSelector,
)

from .const import CONF_CLIMATES, CONF_PRESETS, DEFAULT_PRESET_NAMES, DOMAIN
from .schedule import parse_presets

CLIMATE_SELECTOR = EntitySelector(EntitySelectorConfig(domain="climate", multiple=True))


def _clean_presets(raw: str) -> str | None:
    presets = parse_presets(raw)
    return ", ".join(p["name"] for p in presets) if presets else None


class HeatingScheduleConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            presets = _clean_presets(user_input[CONF_PRESETS])
            if presets is None:
                errors[CONF_PRESETS] = "no_presets"
            else:
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data={**user_input, CONF_PRESETS: presets},
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME): TextSelector(),
                vol.Required(CONF_CLIMATES): CLIMATE_SELECTOR,
                vol.Required(
                    CONF_PRESETS, default=", ".join(DEFAULT_PRESET_NAMES)
                ): TextSelector(),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return HeatingScheduleOptionsFlow()


class HeatingScheduleOptionsFlow(OptionsFlow):
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        current = {**self.config_entry.data, **self.config_entry.options}
        if user_input is not None:
            presets = _clean_presets(user_input[CONF_PRESETS])
            if presets is None:
                errors[CONF_PRESETS] = "no_presets"
            else:
                return self.async_create_entry(data={**user_input, CONF_PRESETS: presets})

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_CLIMATES, default=current.get(CONF_CLIMATES, [])
                ): CLIMATE_SELECTOR,
                vol.Required(
                    CONF_PRESETS, default=current.get(CONF_PRESETS, "")
                ): TextSelector(),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
