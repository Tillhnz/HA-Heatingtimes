"""Konstanten für die Heizplan-Integration."""
from __future__ import annotations

from typing import Final

DOMAIN: Final = "heating_schedule"
STORAGE_VERSION: Final = 1

CONF_CLIMATES: Final = "climate_entities"
CONF_PRESETS: Final = "presets"

DAYS: Final = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

DEFAULT_PRESET_NAMES: Final = ["Komfort", "Eco", "Nacht", "Abwesend"]
DEFAULT_TEMPS: Final = {
    "komfort": 21.0,
    "eco": 19.0,
    "nacht": 17.0,
    "abwesend": 15.0,
}
DEFAULT_TEMP: Final = 20.0

MIN_TEMP: Final = 5.0
MAX_TEMP: Final = 30.0
TEMP_STEP: Final = 0.5

OPTION_SCHEDULE: Final = "Zeitplan"
OPTION_OFF: Final = "Aus"
RESERVED_NAMES: Final = {OPTION_SCHEDULE.lower(), OPTION_OFF.lower()}

URL_BASE: Final = "/heating_schedule_static"
CARD_FILENAME: Final = "heating-schedule-card.js"

SERVICE_SET_SCHEDULE: Final = "set_schedule"
SERVICE_APPLY: Final = "apply"

ATTR_DAYS: Final = "days"
ATTR_BLOCKS: Final = "blocks"
