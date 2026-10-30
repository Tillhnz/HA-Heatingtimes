# Heizplan für Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)

Schöne Wochenzeitpläne fürs Heizen – als echte `schedule.*`-Entität, bedienbar über eine Dashboard-Karte im Stil der Tado-App. Die Thermostate selbst steuerst du mit einer anderen Integration, z. B. **[RoomMind](https://github.com/snazzybean/roommind)**.

- **Pro Zone eine Zeitplan-Entität** (`schedule.wohnzimmer_zeitplan`), die sich wie ein normaler Zeitplan-Helfer verhält
- **Temperatur je Block:** Jeder Zeitblock trägt `temperature` in seinen Daten. RoomMind übernimmt diese Temperatur direkt als Solltemperatur.
- **Temperaturen sind Variablen:** Jedes Preset (Komfort, Eco, Nacht, …) ist eine `number`-Entität. Änderst du „Komfort“ von 21° auf 21,5°, ändern sich alle Komfort-Blöcke mit.
- **Dashboard-Karte:** aktuelle Solltemperatur, nächster Wechsel, Presets mit − / +, 24-h-Zeitleiste pro Tag, Blockeditor, „Speichern für Mo–Fr / Sa+So / Alle Tage“
- Keine Thermostat-Auswahl, kein YAML, die Karte wird automatisch geladen

## Installation

### Über HACS
1. HACS → ⋮ → **Benutzerdefinierte Repositories** → `https://github.com/Tillhnz/HA-Heatingtimes`, Kategorie **Integration**
2. „Heizplan“ installieren und Home Assistant neu starten
3. **Einstellungen → Geräte & Dienste → Integration hinzufügen → Heizplan**

### Manuell
Ordner `custom_components/heating_schedule` nach `config/custom_components/` kopieren und neu starten.

## Einrichtung

Pro Raum eine Zone anlegen: **Name** (z. B. Wohnzimmer) und **Temperatur-Presets** (Standard: Komfort, Eco, Nacht, Abwesend). Die Presets lassen sich später über **Konfigurieren** ändern.

| Entität | Zweck |
|---|---|
| `schedule.wohnzimmer_zeitplan` | Der Wochenplan. State `on`, Attribute `temperature`, `preset`, `preset_name` zeigen den aktuellen Block |
| `number.wohnzimmer_temperatur_komfort` usw. | Die Temperatur-Variablen |

## Mit RoomMind verwenden

1. In RoomMind beim Raum unter **Zeitplan** die Entität `schedule.wohnzimmer_zeitplan` auswählen.
2. Fertig: RoomMind liest per `schedule.get_schedule` die Blöcke und nutzt die `temperature` des aktiven Blocks als Ziel. Abwesenheit, Urlaub und manuelle Overrides von RoomMind haben weiterhin Vorrang.

Da die Blöcke den ganzen Tag lückenlos abdecken, ist der Zeitplan immer „an“. Die Komfort/Eco-Temperaturen in RoomMind greifen daher nur als Rückfallwert.

## Dashboard-Karte

Im Dashboard: **Karte hinzufügen → „Heizplan“**, oder YAML:

```yaml
type: custom:heating-schedule-card
entity: schedule.wohnzimmer_zeitplan
# optional:
title: Wohnzimmer
temperature_entity: sensor.wohnzimmer_temperatur   # oder climate.* für Raumtemperatur + Luftfeuchte
show_presets: true
```

Falls die Karte nach einem Update nicht erscheint: Browser-Cache leeren bzw. App neu laden.

## Dienst `heating_schedule.set_schedule`

```yaml
action: heating_schedule.set_schedule
data:
  zone_id: schedule.wohnzimmer_zeitplan   # oder der Zonenname
  days: [mon, tue, wed, thu, fri]
  blocks:
    - { start: "00:00", preset: nacht }
    - { start: "06:30", preset: komfort }
    - { start: "22:00", preset: nacht }
```
Preset-Keys sind die kleingeschriebenen Namen (`Büro` → `buero`). Zeitplan und Temperaturen werden in `.storage/heating_schedule.<id>` gespeichert.

## Lizenz
MIT
