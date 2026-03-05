#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════╗
║   Wetter-Display – Pimoroni Unicorn HAT Mini (17×7)      ║
║   Raspberry Pi Hardware-Version                          ║
║   Voraussetzung: pip3 install unicornhatmini requests    ║
║                  pip3 install gpiozero                   ║
║   Starten: python3 wetter_unicornhatmini.py              ║
║                                                          ║
║   Button A = Display starten (10 Zyklen)                 ║
║   Button B = Display sofort stoppen                      ║
║   Button X = Display Dauerbetrieb                        ║
║   Button Y = Gruss-Sequenz (Herz + Text + Wetter-Icon)  ║
║                                                          ║
║   Konfiguration: config.json (im selben Verzeichnis)     ║
║   Autostart: systemd Service (wetterstation.service)     ║
╚══════════════════════════════════════════════════════════╝
"""

import json
import logging
import os
import time
import threading
import requests
from datetime import datetime, date
from unicornhatmini import UnicornHATMini
from gpiozero import Button

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("wetterstation")

# ── Konfiguration laden ─────────────────────────────────────────────────────
def load_config():
    config_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "config.json"
    )
    try:
        with open(config_path) as f:
            return json.load(f)
    except FileNotFoundError:
        log.info("Keine config.json gefunden – verwende Standardwerte")
        return {}
    except json.JSONDecodeError as e:
        log.warning("config.json Parse-Fehler: %s – verwende Standardwerte", e)
        return {}

cfg = load_config()

# ── Einstellungen ────────────────────────────────────────────────────────────
_display = cfg.get("display", {})
SCROLL_SPEED   = _display.get("scroll_speed", 0.06)
ICON_SHOW_TIME = _display.get("icon_show_time", 5)
BRIGHTNESS     = _display.get("brightness", 0.4)
DISPLAY_CYCLES = _display.get("display_cycles", 10)
CONTINUOUS     = -1

FETCH_INTERVAL = cfg.get("fetch_interval", 1800)

_location = cfg.get("location", {})
LAT = _location.get("lat", 47.3769)
LON = _location.get("lon", 8.5417)
LOCATION_NAME = _location.get("name", "Zuerich")

GREETING_TEMPLATE = cfg.get(
    "greeting_text",
    "Hallo Carla, hallo Maura, heute wird es {t_max}°C warm. Tschuss!"
)

_autostart = cfg.get("autostart", {})
AUTOSTART_ENABLED = _autostart.get("enabled", False)
AUTOSTART_HOUR    = _autostart.get("hour", 7)
AUTOSTART_MINUTE  = _autostart.get("minute", 0)

# ── Farben ───────────────────────────────────────────────────────────────────
_colors = cfg.get("colors", {})

def _c(name, default):
    val = _colors.get(name, default)
    return tuple(val) if isinstance(val, list) else val

OFF = (  0,   0,   0)
SUN = _c("sun",     (220,  40,  80))
CLO = _c("cloud",   (180, 140, 220))
RAI = _c("rain",    ( 60,  60, 200))
SNO = _c("snow",    (210, 195, 240))
THU = _c("thunder", (120,   0, 180))
ORG = _c("orange",  (200,  30, 100))
STR = _c("star",    (160, 160, 230))
GRN = _c("green",   (160,  80, 200))
HRT = _c("heart",   (255,  20,  80))

DISPLAY_W = 17
DISPLAY_H =  7

# ── Icons ────────────────────────────────────────────────────────────────────
ICON_SUN = [
    [OFF, OFF, SUN, OFF, OFF],
    [OFF, SUN, SUN, SUN, OFF],
    [SUN, SUN, SUN, SUN, SUN],
    [OFF, SUN, SUN, SUN, OFF],
    [OFF, OFF, SUN, OFF, OFF],
]
ICON_CLOUD = [
    [OFF, CLO, CLO, OFF, OFF],
    [CLO, CLO, CLO, CLO, OFF],
    [CLO, CLO, CLO, CLO, CLO],
    [CLO, CLO, CLO, CLO, CLO],
    [OFF, CLO, CLO, CLO, OFF],
]
ICON_PARTLY = [
    [OFF, SUN, SUN, OFF, OFF],
    [SUN, ORG, ORG, CLO, OFF],
    [SUN, ORG, CLO, CLO, CLO],
    [OFF, CLO, CLO, CLO, CLO],
    [OFF, OFF, CLO, CLO, OFF],
]
ICON_RAIN = [
    [OFF, CLO, CLO, CLO, OFF],
    [CLO, CLO, CLO, CLO, CLO],
    [RAI, OFF, RAI, OFF, RAI],
    [OFF, RAI, OFF, RAI, OFF],
    [RAI, OFF, RAI, OFF, RAI],
]
ICON_DRIZZLE = [
    [OFF, CLO, CLO, CLO, OFF],
    [CLO, CLO, CLO, CLO, CLO],
    [STR, OFF, STR, OFF, STR],
    [OFF, STR, OFF, STR, OFF],
    [OFF, OFF, OFF, OFF, OFF],
]
ICON_SNOW = [
    [OFF, SNO, OFF, SNO, OFF],
    [SNO, OFF, SNO, OFF, SNO],
    [OFF, SNO, SNO, SNO, OFF],
    [SNO, OFF, SNO, OFF, SNO],
    [OFF, SNO, OFF, SNO, OFF],
]
ICON_THUNDER = [
    [OFF, CLO, CLO, CLO, OFF],
    [CLO, CLO, CLO, CLO, CLO],
    [OFF, OFF, THU, OFF, OFF],
    [OFF, THU, OFF, OFF, OFF],
    [OFF, OFF, THU, OFF, OFF],
]
ICON_NIGHT = [
    [OFF, OFF, SUN, SUN, OFF],
    [OFF, SUN, OFF, SUN, OFF],
    [SUN, OFF, OFF, SUN, OFF],
    [OFF, SUN, OFF, SUN, OFF],
    [OFF, OFF, SUN, SUN, OFF],
]
ICON_FOG = [
    [CLO, CLO, CLO, CLO, CLO],
    [OFF, OFF, OFF, OFF, OFF],
    [CLO, CLO, CLO, CLO, CLO],
    [OFF, OFF, OFF, OFF, OFF],
    [CLO, CLO, CLO, CLO, CLO],
]
ICON_HEART = [
    [OFF, HRT, OFF, HRT, OFF],
    [HRT, HRT, HRT, HRT, HRT],
    [HRT, HRT, HRT, HRT, HRT],
    [OFF, HRT, HRT, HRT, OFF],
    [OFF, OFF, HRT, OFF, OFF],
]

def wmo_to_icon(code, hour):
    if code == 0:
        return ICON_SUN if 6 <= hour < 20 else ICON_NIGHT
    elif code in (1, 2):
        return ICON_PARTLY
    elif code == 3:
        return ICON_CLOUD
    elif code in (45, 48):
        return ICON_FOG
    elif code in (51, 53, 55, 56, 57):
        return ICON_DRIZZLE
    elif code in (61, 63, 65, 66, 67, 80, 81, 82):
        return ICON_RAIN
    elif code in (71, 73, 75, 77, 85, 86):
        return ICON_SNOW
    elif code in (95, 96, 99):
        return ICON_THUNDER
    else:
        return ICON_CLOUD

# ── Font ─────────────────────────────────────────────────────────────────────
FONT = {
    '0': ['0110','1001','1001','1001','0110'],
    '1': ['0010','0110','0010','0010','0111'],
    '2': ['0110','1001','0010','0100','1111'],
    '3': ['1110','0001','0110','0001','1110'],
    '4': ['1001','1001','1111','0001','0001'],
    '5': ['1111','1000','1110','0001','1110'],
    '6': ['0110','1000','1110','1001','0110'],
    '7': ['1111','0001','0010','0100','0100'],
    '8': ['0110','1001','0110','1001','0110'],
    '9': ['0110','1001','0111','0001','0110'],
    '.': ['0000','0000','0000','0000','0100'],
    ',': ['0000','0000','0000','0100','1000'],
    '-': ['0000','0000','1110','0000','0000'],
    '!': ['0100','0100','0100','0000','0100'],
    ' ': ['0000','0000','0000','0000','0000'],
    '°': ['0110','0110','0000','0000','0000'],
    'A': ['0110','1001','1111','1001','1001'],
    'C': ['0111','1000','1000','1000','0111'],
    'G': ['0110','1000','1011','1001','0110'],
    'H': ['1001','1001','1111','1001','1001'],
    'J': ['0001','0001','0001','1001','0110'],
    'K': ['1001','1010','1100','1010','1001'],
    'M': ['1001','1111','1001','1001','1001'],
    'N': ['1001','1101','1011','1001','1001'],
    'R': ['1110','1001','1110','1100','1010'],
    'T': ['1110','0100','0100','0100','0100'],
    'W': ['1001','1001','1001','1111','0110'],
    'a': ['0000','0110','1010','1110','1001'],
    'd': ['0001','0001','0111','1001','0111'],
    'e': ['0000','0110','1110','1000','0110'],
    'g': ['0000','0111','1010','0111','0001'],
    'h': ['1000','1000','1110','1001','1001'],
    'i': ['0110','0000','0110','0110','0110'],
    'l': ['0110','0010','0010','0010','0111'],
    'n': ['0000','1100','1010','1010','1010'],
    'o': ['0000','0110','1001','1001','0110'],
    'r': ['0000','1011','1100','1000','1000'],
    's': ['0000','0110','1100','0011','1110'],
    't': ['0100','1110','0100','0100','0011'],
    'u': ['0000','1001','1001','1001','0110'],
    'w': ['0000','1001','1001','1111','0110'],
    'x': ['0000','1010','0100','1010','0000'],
}

def text_to_columns(text, fg=(255, 200, 0)):
    columns = []
    y_offset = 1
    for char in text:
        bitmap = FONT.get(char, FONT[' '])
        for col in range(4):
            col_pixels = []
            for row in range(DISPLAY_H):
                if row < y_offset or row >= y_offset + 5:
                    col_pixels.append(OFF)
                else:
                    fr = row - y_offset
                    col_pixels.append(fg if bitmap[fr][col] == '1' else OFF)
            columns.append(col_pixels)
        columns.append([OFF] * DISPLAY_H)
    return columns

def format_temp(value):
    if value == int(value):
        return str(int(value))
    return str(value)

# ── API ──────────────────────────────────────────────────────────────────────
def fetch_weather(max_retries=3):
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={LAT}&longitude={LON}"
        "&hourly=weathercode,temperature_2m"
        "&daily=temperature_2m_max,temperature_2m_min"
        "&timezone=Europe%2FZurich&forecast_days=1"
    )
    for attempt in range(max_retries):
        try:
            r = requests.get(url, timeout=15)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            wait = 2 ** attempt * 5
            log.warning(
                "Fetch-Versuch %d/%d fehlgeschlagen: %s. Retry in %ds",
                attempt + 1, max_retries, e, wait
            )
            if attempt < max_retries - 1:
                time.sleep(wait)
    raise requests.RequestException("Alle Fetch-Versuche fehlgeschlagen")

def dominant_code(codes, times, hour_range):
    vals = [codes[i] for i, t in enumerate(times)
            if 'T' in t and int(t.split('T')[1][:2]) in hour_range]
    return max(set(vals), key=vals.count) if vals else 0

def parse_weather(data):
    times = data['hourly']['time']
    codes = data['hourly']['weathercode']
    t_max = round(data['daily']['temperature_2m_max'][0], 1)
    t_min = round(data['daily']['temperature_2m_min'][0], 1)

    RAIN_CODES = {51,53,55,56,57,61,63,65,66,67,80,81,82,95,96,99}
    regen = any(
        codes[i] in RAIN_CODES
        for i, t in enumerate(times)
        if 'T' in t and 6 <= int(t.split('T')[1][:2]) <= 22
    )
    return {
        'morning': wmo_to_icon(dominant_code(codes, times, range(6,  12)), 9),
        'midday':  wmo_to_icon(dominant_code(codes, times, range(12, 17)), 14),
        'evening': wmo_to_icon(dominant_code(codes, times, range(17, 22)), 19),
        't_max': t_max, 't_min': t_min, 'regen': regen,
    }

# ── HAT-Hilfsfunktionen ─────────────────────────────────────────────────────
def hat_clear(hat):
    hat.clear()
    hat.show()

def hat_set_icon(hat, icon, x_offset):
    for row_i, row in enumerate(icon):
        for col_i, color in enumerate(row):
            hat.set_pixel(x_offset + col_i, 1 + row_i, *color)

def hat_scroll(hat, text, color=(255, 200, 0), speed=None):
    if speed is None:
        speed = SCROLL_SPEED
    columns = text_to_columns(text, fg=color)
    padded  = [[OFF] * DISPLAY_H] * DISPLAY_W + columns + [[OFF] * DISPLAY_H] * DISPLAY_W
    for start in range(len(padded) - DISPLAY_W + 1):
        hat.clear()
        for x in range(DISPLAY_W):
            for y in range(DISPLAY_H):
                r, g, b = padded[start + x][y]
                hat.set_pixel(x, y, r, g, b)
        hat.show()
        time.sleep(speed)

# ── Fehler-Blink ─────────────────────────────────────────────────────────────
def error_blink(hat):
    for _ in range(4):
        hat.clear()
        for x in range(DISPLAY_W):
            for y in range(DISPLAY_H):
                hat.set_pixel(x, y, 120, 0, 0)
        hat.show()
        time.sleep(0.3)
        hat_clear(hat)
        time.sleep(0.3)

# ── Gruss-Sequenz (Button Y) ────────────────────────────────────────────────
def greeting_sequence(hat, weather_data, lock):
    """3x Herz blinken → Gruss scrollen → Wetter-Icon anzeigen."""
    with lock:
        w = weather_data.copy() if weather_data else None

    if not w:
        log.warning("Gruss: Keine Wetterdaten vorhanden.")
        return

    # 1) Herz 3x blinken (zentriert bei x=6)
    for _ in range(3):
        hat.clear()
        hat_set_icon(hat, ICON_HEART, 6)
        hat.show()
        time.sleep(0.6)
        hat_clear(hat)
        time.sleep(0.3)

    # 2) Gruss-Text scrollen
    t_max = format_temp(w['t_max'])
    text = f"  {GREETING_TEMPLATE.format(t_max=t_max)}  "
    hat_scroll(hat, text, color=(255, 20, 80), speed=SCROLL_SPEED)

    # 3) Wetter-Icon anzeigen: Wolke bei Regen, Sonne bei kein Regen
    hat.clear()
    icon = ICON_CLOUD if w['regen'] else ICON_SUN
    hat_set_icon(hat, icon, 6)
    hat.show()
    time.sleep(4)
    hat_clear(hat)

# ── Background Fetch Thread ─────────────────────────────────────────────────
def weather_fetch_loop(weather_data, lock, stop_event):
    """Lädt Wetterdaten alle FETCH_INTERVAL Sekunden im Hintergrund."""
    while not stop_event.is_set():
        log.info("Lade Wetterdaten …")
        try:
            raw = fetch_weather()
            parsed = parse_weather(raw)
            with lock:
                weather_data.update(parsed)
                weather_data['_last_fetch'] = time.time()
                weather_data['_stale'] = False
            regen_str = "Ja" if parsed['regen'] else "Nein"
            log.info(
                "Min %s°C / Max %s°C | Regen: %s",
                format_temp(parsed['t_min']),
                format_temp(parsed['t_max']),
                regen_str,
            )
        except Exception as e:
            log.error("Wetterdaten-Abruf fehlgeschlagen: %s", e)
            with lock:
                if weather_data:
                    weather_data['_stale'] = True
                    age_min = (time.time() - weather_data.get('_last_fetch', 0)) / 60
                    log.info("Verwende letzte bekannte Daten (Alter: %d min)", age_min)

        for _ in range(FETCH_INTERVAL):
            if stop_event.is_set():
                return
            time.sleep(1)

# ── Autostart-Scheduler ─────────────────────────────────────────────────────
def autostart_scheduler(activate_callback, stop_event):
    """Aktiviert das Display täglich zur konfigurierten Uhrzeit."""
    last_triggered_date = None
    while not stop_event.is_set():
        now = datetime.now()
        target_passed = (
            now.hour > AUTOSTART_HOUR
            or (now.hour == AUTOSTART_HOUR and now.minute >= AUTOSTART_MINUTE)
        )
        if target_passed and last_triggered_date != now.date():
            log.info(
                "Autostart: Display aktiviert um %02d:%02d",
                AUTOSTART_HOUR, AUTOSTART_MINUTE,
            )
            activate_callback()
            last_triggered_date = now.date()

        for _ in range(30):
            if stop_event.is_set():
                return
            time.sleep(1)

# ── Hauptprogramm ───────────────────────────────────────────────────────────
def main():
    hat = UnicornHATMini()
    hat.set_brightness(BRIGHTNESS)
    hat_clear(hat)

    # Shared State
    weather_data = {}
    lock = threading.Lock()
    cycles_remaining = 0
    stop_event = threading.Event()

    # ── Background-Fetch starten ──
    fetch_thread = threading.Thread(
        target=weather_fetch_loop,
        args=(weather_data, lock, stop_event),
        daemon=True,
    )
    fetch_thread.start()

    # ── Buttons ──
    button_a = Button(5)
    button_b = Button(6)
    button_x = Button(16)
    button_y = Button(24)

    def on_button_a():
        nonlocal cycles_remaining
        cycles_remaining = DISPLAY_CYCLES
        log.info("Button A → Display AN (%d Zyklen)", DISPLAY_CYCLES)

    def on_button_b():
        nonlocal cycles_remaining
        cycles_remaining = 0
        hat_clear(hat)
        log.info("Button B → Display AUS")

    def on_button_x():
        nonlocal cycles_remaining
        cycles_remaining = CONTINUOUS
        log.info("Button X → Dauerbetrieb")

    def on_button_y():
        threading.Thread(
            target=greeting_sequence,
            args=(hat, weather_data, lock),
            daemon=True,
        ).start()

    button_a.when_pressed = on_button_a
    button_b.when_pressed = on_button_b
    button_x.when_pressed = on_button_x
    button_y.when_pressed = on_button_y

    # ── Autostart-Scheduler starten ──
    if AUTOSTART_ENABLED:
        def activate_continuous():
            nonlocal cycles_remaining
            cycles_remaining = CONTINUOUS

        scheduler_thread = threading.Thread(
            target=autostart_scheduler,
            args=(activate_continuous, stop_event),
            daemon=True,
        )
        scheduler_thread.start()
        log.info(
            "Autostart geplant fuer %02d:%02d",
            AUTOSTART_HOUR, AUTOSTART_MINUTE,
        )

    log.info("Wetter-Display gestartet – %s", LOCATION_NAME)
    log.info("A = %d Zyklen | B = Stop | X = Dauerbetrieb | Y = Gruss", DISPLAY_CYCLES)
    log.info("Warte auf erste Wetterdaten …")

    # Warte bis erste Daten da sind
    while not weather_data:
        time.sleep(0.5)
    log.info("Bereit.")

    # ── Main Loop ──
    while True:
        if cycles_remaining != 0:
            with lock:
                w = weather_data.copy()

            # Icons anzeigen
            hat.clear()
            for icon, x_off in [
                (w['morning'], 0),
                (w['midday'],  6),
                (w['evening'], 12),
            ]:
                hat_set_icon(hat, icon, x_off)

            # Stale-Indikator: roter Punkt oben rechts
            if w.get('_stale'):
                hat.set_pixel(16, 0, 120, 0, 0)

            hat.show()

            # Interruptible sleep für Icon-Anzeige
            for _ in range(int(ICON_SHOW_TIME / 0.2)):
                if cycles_remaining == 0:
                    break
                time.sleep(0.2)

            if cycles_remaining == 0:
                hat_clear(hat)
                continue

            # Temperatur scrollen
            hat_scroll(hat,
                       f"  Min {format_temp(w['t_min'])}°C  "
                       f"Max {format_temp(w['t_max'])}°C  ",
                       color=(220, 40, 80))

            if cycles_remaining == 0:
                hat_clear(hat)
                continue

            time.sleep(1)

            # Regen scrollen
            regen_label = "Regen Ja" if w['regen'] else "Regen Nein"
            regen_color = (60, 60, 200) if w['regen'] else (160, 80, 200)
            hat_scroll(hat, f"  {regen_label}  ", color=regen_color)

            # Zyklus runterzählen (nur wenn nicht Dauerbetrieb)
            if cycles_remaining > 0:
                cycles_remaining -= 1
                if cycles_remaining == 0:
                    hat_clear(hat)
                    log.info("%d Zyklen abgeschlossen – Display AUS", DISPLAY_CYCLES)

            time.sleep(1)
        else:
            # Display aus – idle, wenig CPU
            time.sleep(0.2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("Beendet (KeyboardInterrupt).")
    except Exception as e:
        log.critical("Unerwarteter Fehler: %s", e, exc_info=True)
