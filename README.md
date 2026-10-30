# Heizplan für Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)

Wochenzeitpläne für deine Thermostate, bedienbar über eine Dashboard-Karte im Stil der Tado-App.

- **Zeitblöcke pro Wochentag** (z. B. 06:00 Komfort, 08:30 Eco, 22:30 Nacht)
- **Temperaturen sind Variablen:** Jedes Preset (Komfort, Eco, Nacht, …) ist eine eigene `number`-Entität. Änderst du „Komfort“ von 21° auf 21,5°, gilt das sofort in allen Blöcken, die Komfort nutzen.
- **Dashboard-Karte:** Solltemperatur, Raumtemperatur, nächster Wechsel, Modus-Chips, Presets mit − / +, 24-h-Zeitleiste, Blockeditor und „Speichern für Mo–Fr / Sa+So / Alle Tage“
- **Modus pro Zone:** Zeitplan, festes Preset oder Aus
- **Manuelle Änderungen bleiben bis zum nächsten Block** (wie bei Tado), weil Temperaturen nur bei Blockwechseln gesendet werden
- Mehrere Thermostate pro Zone, beliebig viele Zonen
- Keine YAML-Konfiguration, kein separates Laden der Karte nötig

## Installation

### Über HACS
1. HACS → ⋮ → **Benutzerdefinierte Repositories** → URL dieses Repos, Kategorie **Integration**
2. „Heizplan“ installieren und Home Assistant neu starten
3. **Einstellungen → Geräte & Dienste → Integration hinzufügen → Heizplan**

### Manuell
Ordner `custom_components/heating_schedule` nach `config/custom_components/` kopieren und neu starten.

## Einrichtung

Pro Raum eine Zone anlegen:

| Feld | Beispiel |
|---|---|
| Name der Zone | Wohnzimmer |
| Thermostate | `climate.wohnzimmer_heizung`, `climate.wohnzimmer_fenster` |
| Temperatur-Presets | Komfort, Eco, Nacht, Abwesend |

Thermostate und Presets lassen sich später über **Konfigurieren** ändern.

### Entstehende Entitäten (Beispiel „Wohnzimmer“)

| Entität | Zweck |
|---|---|
| `sensor.wohnzimmer_solltemperatur` | Aktuelle Solltemperatur, trägt den Zeitplan für die Karte |
| `select.wohnzimmer_modus` | Zeitplan / Komfort / Eco / … / Aus |
| `number.wohnzimmer_temperatur_komfort` usw. | Die Temperatur-Variablen |

## Dashboard-Karte

Die Karte wird automatisch geladen. Im Dashboard: **Karte hinzufügen → „Heizplan“**, oder YAML:

```yaml
type: custom:heating-schedule-card
entity: sensor.wohnzimmer_solltemperatur
# optional:
title: Wohnzimmer
show_presets: true
show_mode: true
```

Falls die Karte nach einem Update nicht erscheint: Browser-Cache leeren bzw. App neu laden.

## Automationen & Dienste

Die Preset-Temperaturen sind normale `number`-Entitäten, z. B. für einen Urlaubsmodus:

```yaml
action: select.select_option
target:
  entity_id: select.wohnzimmer_modus
data:
  option: Abwesend
```

### `heating_schedule.set_schedule`
```yaml
action: heating_schedule.set_schedule
data:
  zone_id: Wohnzimmer          # Name oder Entry-ID
  days: [mon, tue, wed, thu, fri]
  blocks:
    - { start: "00:00", preset: nacht }
    - { start: "06:30", preset: komfort }
    - { start: "22:00", preset: nacht }
```
Preset-Keys sind die kleingeschriebenen Namen (`Büro` → `buero`).

### `heating_schedule.apply`
Sendet die aktuelle Solltemperatur erneut an alle Thermostate und verwirft manuelle Änderungen.

## Verhalten im Detail

- Temperaturen werden gesendet beim Start, bei jedem Blockwechsel, bei Änderung des laufenden Presets, des Modus oder des Zeitplans und wenn ein Thermostat wieder online kommt.
- Ein ausgeschaltetes Thermostat wird beim nächsten Heizblock auf `heat` gestellt; Modus „Aus“ schaltet die Thermostate aus.
- Zeitplan, Temperaturen und Modus werden in `.storage/heating_schedule.<id>` gespeichert und überstehen Neustarts.

## Lizenz
MIT
