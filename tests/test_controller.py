"""Regressionstest: Speichern muss für HA als Zustandsänderung erkennbar sein."""
import asyncio
import importlib.util
from pathlib import Path
import sys
import types

ROOT = Path(__file__).parents[1] / "custom_components/heating_schedule"


def _stub_homeassistant():
    """Minimale Platzhalter für die HA-Module, die controller.py importiert."""
    mods = {
        "homeassistant": {},
        "homeassistant.config_entries": {"ConfigEntry": object},
        "homeassistant.const": {"CONF_NAME": "name"},
        "homeassistant.core": {"CALLBACK_TYPE": object, "HomeAssistant": object, "callback": lambda f: f},
        "homeassistant.helpers": {},
        "homeassistant.helpers.storage": {},
    }
    for name, attrs in mods.items():
        mod = sys.modules.setdefault(name, types.ModuleType(name))
        for key, value in attrs.items():
            setattr(mod, key, value)

    class Store:
        def __init__(self, *args):
            self.saved = None

        async def async_load(self):
            return None

        def async_delay_save(self, func, delay):
            self.saved = func()

    sys.modules["homeassistant.helpers.storage"].Store = Store


def _load_package():
    _stub_homeassistant()
    pkg = types.ModuleType("heating_schedule")
    pkg.__path__ = [str(ROOT)]
    sys.modules["heating_schedule"] = pkg
    for name in ("const", "schedule", "controller"):
        spec = importlib.util.spec_from_file_location(f"heating_schedule.{name}", ROOT / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    return sys.modules["heating_schedule.controller"]


controller_mod = _load_package()


def _make_controller():
    entry = types.SimpleNamespace(entry_id="abc", data={"name": "Wohnzimmer", "presets": "Komfort, Eco, Nacht"},
                                  options={}, title="Wohnzimmer")
    ctrl = controller_mod.ZoneController(object(), entry)
    asyncio.run(ctrl.async_load())
    return ctrl


def test_save_multiple_days_is_detected_as_change():
    ctrl = _make_controller()
    # So legt HA alte Attribute ab: flache Kopie (ReadOnlyDict(attributes))
    old_attrs = dict({"blocks": ctrl.blocks_snapshot()})

    new_blocks = [{"start": "00:00", "preset": "nacht"}, {"start": "07:15", "preset": "komfort"}]
    ctrl.set_schedule(["mon", "tue", "wed", "thu", "fri"], new_blocks)
    new_attrs = {"blocks": ctrl.blocks_snapshot()}

    assert old_attrs != new_attrs, "HA würde die Änderung nicht erkennen"
    for day in ("mon", "tue", "wed", "thu", "fri"):
        assert new_attrs["blocks"][day] == new_blocks
    assert new_attrs["blocks"]["sat"] == old_attrs["blocks"]["sat"]


def test_days_do_not_share_block_objects():
    ctrl = _make_controller()
    ctrl.set_schedule(["sat", "sun"], [{"start": "00:00", "preset": "eco"}])
    ctrl.schedule["sat"][0]["preset"] = "komfort"
    assert ctrl.schedule["sun"][0]["preset"] == "eco"


def test_listeners_and_storage_are_notified():
    ctrl = _make_controller()
    calls = []
    ctrl.add_listener(lambda: calls.append(1))
    ctrl.set_schedule(["sun"], [{"start": "00:00", "preset": "eco"}])
    assert calls == [1]
    assert ctrl._store.saved["schedule"]["sun"] == [{"start": "00:00", "preset": "eco"}]
