# Wetterstation

Raspberry Pi Wetterstation mit **Pimoroni Unicorn HAT Mini** (17x7 RGB-LED-Matrix).
Zeigt Wetterdaten der [Open-Meteo API](https://open-meteo.com/) als Icons und Scrolltext an.

## Features

- **3 Wetter-Icons** (Morgen / Mittag / Abend) aus WMO-Codes — Sonne, Wolken, Regen, Schnee, Gewitter, Nebel, Nacht
- **Scrolltext**: Min/Max-Temperatur, Regen- und Sonnen-Status mit farbiger Anzeige
- **Persönlicher Gruss** mit Herz-Animation und konfigurierbarem Text
- **Täglicher Autostart** zu konfigurierbarer Uhrzeit
- **4 Hardware-Buttons** (A/B/X/Y) für direkte Steuerung
- **Fernsteuerung per SSH** über Named Pipe (FIFO)
- **Simulator-Modus** für Entwicklung ohne Hardware
- **126 Unit-Tests** mit pytest

## Hardware

- Raspberry Pi (getestet mit Pi 5)
- [Pimoroni Unicorn HAT Mini](https://shop.pimoroni.com/products/unicorn-hat-mini) (17x7 LED)
- 4 integrierte Buttons: A, B, X, Y

## Installation

```bash
# Repository klonen
git clone <repo-url>
cd wetterstation

# Auf dem Pi (mit Hardware-Support)
pip install -e ".[pi]"

# Entwicklung (Tests + Mocking)
pip install -e ".[dev]"
```

**Voraussetzungen**: Python >= 3.9

## Konfiguration

Erstelle eine `config.json` im Projektverzeichnis:

```json
{
  "location": {
    "lat": 47.37,
    "lon": 8.54,
    "name": "Meine Stadt"
  },
  "display": {
    "scroll_speed": 0.06,
    "icon_show_time": 5,
    "brightness": 0.4,
    "display_cycles": 10
  },
  "fetch_interval": 1800,
  "greeting_text": "Hallo! Heute wird es {t_max}°C warm.",
  "autostart": {
    "enabled": true,
    "hour": 7,
    "minute": 0
  },
  "colors": {
    "sun": [220, 40, 80],
    "cloud": [180, 140, 220],
    "rain": [60, 60, 200],
    "snow": [210, 195, 240],
    "thunder": [120, 0, 180],
    "orange": [200, 30, 100],
    "star": [160, 160, 230],
    "green": [160, 80, 200],
    "heart": [255, 20, 80]
  }
}
```

| Feld | Beschreibung | Default |
|------|-------------|---------|
| `location.lat/lon` | Koordinaten für Wetterabfrage | Zürich |
| `location.name` | Anzeigename im Info-Screen | `"Zuerich"` |
| `display.scroll_speed` | Sekunden pro Pixel beim Scrollen | `0.06` |
| `display.icon_show_time` | Sekunden für Icon-Anzeige | `5` |
| `display.brightness` | LED-Helligkeit (0.0–1.0) | `0.4` |
| `display.display_cycles` | Zyklen bei Button A / Command `a` | `10` |
| `fetch_interval` | Sekunden zwischen API-Abfragen | `1800` |
| `greeting_text` | Grusstext, `{t_max}` wird ersetzt | — |
| `autostart.enabled` | Täglicher Autostart an/aus | `true` |
| `autostart.hour/minute` | Uhrzeit für Autostart | `7:00` |
| `colors.*` | RGB-Farben als `[R, G, B]` | siehe oben |

## Verwendung

### Starten

```bash
# Auf dem Pi
python -m wetterstation              # Warten auf Button/Command
python -m wetterstation --start      # Sofort 10 Zyklen starten

# Entwicklung (ohne Hardware)
python -m wetterstation --simulator
```

### Steuerung

| Button | Terminal | FIFO | Funktion |
|--------|----------|------|----------|
| A (1x) | `a` | `echo a > /tmp/wetterstation.cmd` | 10 Zyklen starten |
| A (2x) | `aa` | `echo aa > ...` | Dauerbetrieb |
| B | `b` / `r` | `echo b > ...` | Stop |
| X | `x` | `echo x > ...` | Info (Ort + Aktualisierung) |
| Y | `y` | `echo y > ...` | Gruss-Animation |

### Anzeigezyklus

1. **Icons** — 3 Wetter-Icons nebeneinander (Morgen/Mittag/Abend), 5 Sekunden
2. **Temperatur** — Scrolltext `"0.9 / 14.6"` (Min / Max)
3. **Regen** — `"Regen: Ja"` oder `"Regen: Nein"` (farbig)
4. **Sonne** — `"Sonne: Ja"` oder `"Sonne: Nein"` (farbig)

## Systemd-Service

```bash
# Service installieren
sudo cp wetterstation.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now wetterstation

# Status prüfen
sudo systemctl status wetterstation
journalctl -u wetterstation -f

# Fernsteuerung per SSH
ssh user@hostname "echo a > /tmp/wetterstation.cmd"
ssh user@hostname "echo x > /tmp/wetterstation.cmd"
```

Die `wetterstation.service` muss vor der Installation angepasst werden:
- `User=` auf den eigenen Benutzer setzen
- `WorkingDirectory=` auf das Projektverzeichnis setzen

## Architektur

```
Input-Threads (Buttons, Terminal, FIFO, Scheduler)
        │
        ▼
   Event Queue (thread-safe)
        │
        ▼
   State Machine (Main Thread)
        │
        ▼
   Display (SPI, nur Main Thread)
```

**Prinzip**: Alle Display-Operationen laufen im Main Thread. Input-Threads pushen nur Events in die Queue. Das eliminiert SPI-Threading-Probleme.

| Modul | Verantwortlichkeit |
|-------|-------------------|
| `state.py` | Thread-safe State Machine mit Event Queue |
| `display.py` | Hardware-Abstraktion (DisplayBackend Protocol) |
| `weather.py` | Open-Meteo API-Client + WMO-Code-Parsing |
| `renderer.py` | Pixel-Font, Wetter-Icons, Text-Rendering |
| `animations.py` | Interruptible Animationen (Scroll, Icons, Greeting) |
| `input.py` | Button-Handler, Terminal-Input, FIFO-Input |
| `config.py` | Konfiguration laden + validieren |
| `simulator.py` | In-Memory Display-Backend für Tests |

## Tests

```bash
# Alle Tests
pytest tests/ -v

# Mit Coverage
pytest tests/ --cov=wetterstation

# Einzelnes Modul
pytest tests/test_state.py -v
```

## Projektstruktur

```
wetterstation/
├── config.json               # Laufzeit-Konfiguration
├── pyproject.toml             # Dependencies + Metadata
├── wetterstation.service      # Systemd Service-Datei
├── README.md
│
├── wetterstation/             # Python-Package
│   ├── __init__.py            # Version (2.0.0)
│   ├── __main__.py            # Entry Point + Main Loop
│   ├── state.py               # State Machine
│   ├── config.py              # Konfiguration
│   ├── display.py             # Hardware-Backend
│   ├── simulator.py           # Test-Backend
│   ├── weather.py             # API-Client
│   ├── renderer.py            # Font + Icons
│   ├── animations.py          # Display-Animationen
│   └── input.py               # Eingabe (Buttons/Terminal/FIFO)
│
└── tests/                     # pytest Test-Suite
    ├── conftest.py            # Shared Fixtures
    ├── test_state.py
    ├── test_weather.py
    ├── test_animations.py
    ├── test_renderer.py
    ├── test_config.py
    └── test_display.py
```

## Lizenz

MIT
