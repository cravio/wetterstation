#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════╗
║   Wetter-Display – Pimoroni Unicorn HAT Mini (17×7)      ║
║   Raspberry Pi Hardware-Version                          ║
║   Voraussetzung: pip3 install unicornhatmini requests    ║
║                  pip3 install gpiozero                   ║
║   Starten: python3 wetter_unicornhatmini.py [--start]    ║
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
import sys
import time
import threading
import requests
from datetime import datetime, date
from unicornhatmini import UnicornHATMini
import RPi.GPIO as GPIO

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
    "Hallo Carla, hallo Maura, heute wird es {t_max}°C warm"
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

# ── Interrupt-Event (wird bei jedem Button-Druck gesetzt) ─────────────────────
interrupt = threading.Event()

# ── Icons ────────────────────────────────────────────────────────────────────
ICON_SUN = [
    [SUN, OFF, SUN, OFF, SUN],
    [OFF, SUN, SUN, SUN, OFF],
    [SUN, SUN, SUN, SUN, SUN],
    [OFF, SUN, SUN, SUN, OFF],
    [SUN, OFF, SUN, OFF, SUN],
]
ICON_CLOUD = [
    [OFF, OFF, CLO, OFF, OFF],
    [OFF, CLO, CLO, CLO, OFF],
    [CLO, CLO, CLO, CLO, CLO],
    [CLO, CLO, CLO, CLO, CLO],
    [OFF, OFF, OFF, OFF, OFF],
]
ICON_PARTLY = [
    [OFF, OFF, SUN, OFF, OFF],
    [OFF, SUN, CLO, CLO, OFF],
    [SUN, CLO, CLO, CLO, CLO],
    [OFF, CLO, CLO, CLO, CLO],
    [OFF, OFF, OFF, OFF, OFF],
]
ICON_RAIN = [
    [OFF, CLO, CLO, CLO, OFF],
    [CLO, CLO, CLO, CLO, CLO],
    [OFF, OFF, OFF, OFF, OFF],
    [RAI, OFF, RAI, OFF, RAI],
    [OFF, RAI, OFF, RAI, OFF],
]
ICON_DRIZZLE = [
    [OFF, CLO, CLO, CLO, OFF],
    [CLO, CLO, CLO, CLO, CLO],
    [OFF, OFF, OFF, OFF, OFF],
    [OFF, STR, OFF, STR, OFF],
    [OFF, OFF, OFF, OFF, OFF],
]
ICON_SNOW = [
    [OFF, CLO, CLO, CLO, OFF],
    [CLO, CLO, CLO, CLO, CLO],
    [OFF, OFF, OFF, OFF, OFF],
    [SNO, OFF, SNO, OFF, SNO],
    [OFF, SNO, OFF, SNO, OFF],
]
ICON_THUNDER = [
    [OFF, CLO, CLO, CLO, OFF],
    [CLO, CLO, CLO, CLO, CLO],
    [OFF, OFF, THU, THU, OFF],
    [OFF, THU, THU, OFF, OFF],
    [OFF, OFF, OFF, THU, OFF],
]
ICON_NIGHT = [
    [OFF, OFF, SUN, SUN, OFF],
    [OFF, SUN, OFF, OFF, OFF],
    [OFF, SUN, OFF, OFF, OFF],
    [OFF, SUN, OFF, OFF, OFF],
    [OFF, OFF, SUN, SUN, OFF],
]
ICON_FOG = [
    [OFF, OFF, OFF, OFF, OFF],
    [CLO, CLO, CLO, CLO, CLO],
    [OFF, OFF, OFF, OFF, OFF],
    [OFF, CLO, CLO, CLO, OFF],
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
    '1': ['0100','1100','0100','0100','1110'],
    '2': ['0110','1001','0010','0100','1111'],
    '3': ['1110','0001','0110','0001','1110'],
    '4': ['1010','1010','1111','0010','0010'],
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
    'C': ['0110','1000','1000','1000','0110'],
    'G': ['0110','1000','1011','1001','0110'],
    'H': ['1001','1001','1111','1001','1001'],
    'J': ['0011','0001','0001','1001','0110'],
    'K': ['1001','1010','1100','1010','1001'],
    'M': ['1001','1111','1111','1001','1001'],
    'N': ['1001','1101','1011','1001','1001'],
    'R': ['1110','1001','1110','1010','1001'],
    'S': ['0110','1000','0110','0001','0110'],
    'T': ['1110','0100','0100','0100','0100'],
    'W': ['1001','1001','1001','1111','0110'],
    'a': ['0000','0110','0010','1010','0111'],
    'd': ['0001','0001','0111','1001','0111'],
    'e': ['0000','0110','1111','1000','0110'],
    'g': ['0000','0111','1001','0111','0110'],
    'c': ['0000','0110','1000','1000','0110'],
    'h': ['1000','1000','1110','1001','1001'],
    'i': ['0100','0000','0100','0100','0100'],
    'l': ['1100','0100','0100','0100','1110'],
    'm': ['0000','1111','1001','1001','1001'],
    'n': ['0000','1110','1001','1001','1001'],
    'o': ['0000','0110','1001','1001','0110'],
    'r': ['0000','1011','1100','1000','1000'],
    's': ['0000','0110','1100','0011','1110'],
    't': ['0100','1110','0100','0100','0011'],
    'u': ['0000','1001','1001','1001','0110'],
    'w': ['0000','1001','1001','1111','0110'],
    'x': ['0000','1001','0110','0110','1001'],
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
    if not vals:
        return 0
    code_set = set(vals)
    has_sun   = bool(code_set & {0, 1})
    has_cloud = bool(code_set & {2, 3})
    if has_sun and has_cloud:
        sun_count   = sum(1 for v in vals if v in (0, 1))
        cloud_count = sum(1 for v in vals if v in (2, 3))
        total = sun_count + cloud_count
        if total > 0 and min(sun_count, cloud_count) / total >= 0.3:
            return 2
    return max(set(vals), key=vals.count)

def parse_weather(data):
    times = data['hourly']['time']
    codes = data['hourly']['weathercode']
    t_max = round(data['daily']['temperature_2m_max'][0], 1)
    t_min = round(data['daily']['temperature_2m_min'][0], 1)

    now_hour = datetime.now().hour

    RAIN_CODES = {51,53,55,56,57,61,63,65,66,67,80,81,82,95,96,99}
    SUN_CODES  = {0, 1}

    regen = any(
        codes[i] in RAIN_CODES
        for i, t in enumerate(times)
        if 'T' in t and int(t.split('T')[1][:2]) >= now_hour
    )
    sonne = any(
        codes[i] in SUN_CODES
        for i, t in enumerate(times)
        if 'T' in t and int(t.split('T')[1][:2]) >= now_hour
    )

    return {
        'morning': wmo_to_icon(dominant_code(codes, times, range(6,  12)), 9),
        'midday':  wmo_to_icon(dominant_code(codes, times, range(12, 17)), 14),
        'evening': wmo_to_icon(dominant_code(codes, times, range(17, 22)), 19),
        't_max': t_max, 't_min': t_min, 'regen': regen, 'sonne': sonne,
    }

# ── HAT-Hilfsfunktionen ─────────────────────────────────────────────────────
def patch_hat_spi(hat):
    """Pi 5 SPI-Fix: xfer-Pacing (1ms) + Double-Show für beide Hälften."""
    original_xfer = hat.xfer
    original_show = hat.show
    last_xfer = [0.0]

    def paced_xfer(device, pin, command):
        elapsed = time.monotonic() - last_xfer[0]
        if elapsed < 0.001:
            time.sleep(0.001 - elapsed)
        original_xfer(device, pin, command)
        last_xfer[0] = time.monotonic()

    def stable_show():
        original_show()
        time.sleep(0.002)
        original_show()

    hat.xfer = paced_xfer
    hat.show = stable_show

def hat_reset(hat):
    """Kompletter Display-Reset."""
    hat.clear()
    hat.show()
    time.sleep(0.01)

def hat_set_icon(hat, icon, x_offset):
    for row_i, row in enumerate(icon):
        for col_i, color in enumerate(row):
            hat.set_pixel(x_offset + col_i, 1 + row_i, *color)

# ── Interruptible Helpers ────────────────────────────────────────────────────
def isleep(secs):
    """Schläft, bricht aber sofort ab wenn interrupt gesetzt wird.
    Returns True wenn komplett durchgeschlafen, False wenn unterbrochen."""
    end = time.monotonic() + secs
    while time.monotonic() < end:
        if interrupt.is_set():
            return False
        time.sleep(0.02)
    return True

def hat_scroll(hat, text, color=(255, 200, 0), speed=None):
    """Scrollt Text über das Display.
    Bricht sofort ab wenn interrupt gesetzt wird.
    Returns True wenn komplett, False wenn unterbrochen."""
    if speed is None:
        speed = SCROLL_SPEED
    columns = text_to_columns(text, fg=color)
    padded  = [[OFF] * DISPLAY_H] * DISPLAY_W + columns + [[OFF] * DISPLAY_H] * DISPLAY_W
    for start in range(len(padded) - DISPLAY_W + 1):
        if interrupt.is_set():
            return False
        hat.clear()
        for x in range(DISPLAY_W):
            for y in range(DISPLAY_H):
                r, g, b = padded[start + x][y]
                hat.set_pixel(x, y, r, g, b)
        hat.show()
        time.sleep(speed)
    return True

# ── Gruss-Sequenz (Button Y) ────────────────────────────────────────────────
def greeting_sequence(hat, weather_data, lock):
    """3x Herz blinken → Gruss scrollen → Wetter-Icon.
    Komplett interruptible – bricht bei jedem Button-Druck sofort ab.
    Caller macht hat_reset() vor und nach dem Aufruf."""
    with lock:
        w = weather_data.copy() if weather_data else None

    if not w:
        log.warning("Gruss: Keine Wetterdaten vorhanden.")
        return

    # 1) Herz 3x blinken (zentriert bei x=6)
    log.info("  [Gruss] Herz")
    for _ in range(3):
        if interrupt.is_set():
            return
        hat.clear()
        hat_set_icon(hat, ICON_HEART, 6)
        hat.show()
        if not isleep(0.6):
            return
        hat.clear()
        hat.show()
        if not isleep(0.3):
            return

    # 2) Gruss-Text scrollen
    if interrupt.is_set():
        return
    t_max = format_temp(w['t_max'])
    text = f"  {GREETING_TEMPLATE.format(t_max=t_max)}"
    if w['regen']:
        text += " und es regnet"
    if w['sonne']:
        text += " und es scheint die Sonne"
    text += ". Tschuss!  "
    log.info("  [Gruss] Text scrollen")
    if not hat_scroll(hat, text, color=(255, 20, 80), speed=SCROLL_SPEED):
        return

    # 3) Wetter-Icon anzeigen
    if interrupt.is_set():
        return
    hat.clear()
    icon = ICON_CLOUD if w['regen'] else ICON_SUN
    hat_set_icon(hat, icon, 6)
    hat.show()
    log.info("  [Gruss] Wetter-Icon")
    isleep(4)

# ── Fehler-Blink ─────────────────────────────────────────────────────────────
def error_blink(hat):
    for _ in range(4):
        hat.clear()
        for x in range(DISPLAY_W):
            for y in range(DISPLAY_H):
                hat.set_pixel(x, y, 120, 0, 0)
        hat.show()
        time.sleep(0.3)
        hat_reset(hat)
        time.sleep(0.3)

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
            sonne_str = "Ja" if parsed['sonne'] else "Nein"
            log.info(
                "Min %s°C / Max %s°C | Regen: %s | Sonne: %s",
                format_temp(parsed['t_min']),
                format_temp(parsed['t_max']),
                regen_str, sonne_str,
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
    patch_hat_spi(hat)
    hat.set_brightness(BRIGHTNESS)
    hat_reset(hat)

    # Shared State
    weather_data = {}
    lock = threading.Lock()
    cycles_remaining = 0
    if '--start' in sys.argv:
        cycles_remaining = DISPLAY_CYCLES
        log.info("--start → Display AN (%d Zyklen)", DISPLAY_CYCLES)
    fetch_stop = threading.Event()
    button_override = False
    auto_started = False
    greeting_requested = False

    # ── Background-Fetch starten ──
    fetch_thread = threading.Thread(
        target=weather_fetch_loop,
        args=(weather_data, lock, fetch_stop),
        daemon=True,
    )
    fetch_thread.start()

    # ── Buttons (RPi.GPIO, gleicher Handle wie UnicornHATMini, nur Polling) ──
    BUTTON_A = 5
    BUTTON_B = 6
    BUTTON_X = 16
    BUTTON_Y = 24
    ALL_BUTTONS = (BUTTON_A, BUTTON_B, BUTTON_X, BUTTON_Y)

    for pin in ALL_BUTTONS:
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    # ── Button A Doppelklick-Erkennung ──
    DOUBLE_CLICK_WINDOW = 3.0
    last_a_press = [0.0]
    a_click_timer = [None]

    def handle_a_single():
        """Wird nach Ablauf des Doppelklick-Fensters aufgerufen."""
        nonlocal cycles_remaining, button_override, greeting_requested
        interrupt.set()
        cycles_remaining = DISPLAY_CYCLES
        button_override = True
        greeting_requested = False
        log.info("Button A → Display AN (%d Zyklen)", DISPLAY_CYCLES)

    def handle_a_double():
        """Sofort bei Doppelklick."""
        nonlocal cycles_remaining, button_override, greeting_requested
        interrupt.set()
        cycles_remaining = CONTINUOUS
        button_override = True
        greeting_requested = False
        log.info("Button A Doppelklick → Dauerbetrieb")

    def on_button_a():
        now = time.monotonic()
        elapsed = now - last_a_press[0]
        last_a_press[0] = now

        if elapsed <= DOUBLE_CLICK_WINDOW:
            # Doppelklick: Timer abbrechen, Dauerbetrieb
            if a_click_timer[0] is not None:
                a_click_timer[0].cancel()
                a_click_timer[0] = None
            handle_a_double()
        else:
            # Erster Klick: Timer starten, warte auf möglichen zweiten
            if a_click_timer[0] is not None:
                a_click_timer[0].cancel()
            a_click_timer[0] = threading.Timer(DOUBLE_CLICK_WINDOW, handle_a_single)
            a_click_timer[0].daemon = True
            a_click_timer[0].start()

    def on_button_b():
        nonlocal cycles_remaining, button_override, greeting_requested
        interrupt.set()
        cycles_remaining = 0
        button_override = True
        greeting_requested = False
        log.info("Button B → Display AUS")

    info_requested = False

    def on_button_x():
        nonlocal info_requested
        interrupt.set()
        info_requested = True
        log.info("Button X → Info")

    def on_button_y():
        nonlocal cycles_remaining, greeting_requested
        interrupt.set()
        cycles_remaining = 0
        greeting_requested = True
        log.info("Button Y → Gruss")

    def on_button(channel):
        if channel == BUTTON_A:
            on_button_a()
        elif channel == BUTTON_B:
            on_button_b()
        elif channel == BUTTON_X:
            on_button_x()
        elif channel == BUTTON_Y:
            on_button_y()

    def button_poll_loop():
        """Pollt Button-States alle 50ms."""
        prev = {pin: 1 for pin in ALL_BUTTONS}
        while True:
            for pin in ALL_BUTTONS:
                state = GPIO.input(pin)
                if state == 0 and prev[pin] == 1:
                    on_button(pin)
                prev[pin] = state
            time.sleep(0.05)

    threading.Thread(target=button_poll_loop, daemon=True).start()

    # ── Terminal-Eingaben ──
    def stdin_loop():
        """Terminal: a = 10 Zyklen, aa = Dauerbetrieb, b = Stop, x = Info, y = Gruss."""
        for line in sys.stdin:
            cmd = line.strip().lower()
            if cmd == 'aa':
                handle_a_double()
                log.info("Terminal → Dauerbetrieb (aa)")
            elif cmd == 'a':
                handle_a_single()
                log.info("Terminal → %d Zyklen", DISPLAY_CYCLES)
            elif cmd == 'b':
                on_button_b()
            elif cmd == 'x':
                on_button_x()
            elif cmd == 'y':
                on_button_y()

    threading.Thread(target=stdin_loop, daemon=True).start()

    # ── Autostart-Scheduler starten ──
    if AUTOSTART_ENABLED:
        def activate_continuous():
            nonlocal cycles_remaining, button_override
            cycles_remaining = CONTINUOUS
            button_override = False

        scheduler_thread = threading.Thread(
            target=autostart_scheduler,
            args=(activate_continuous, fetch_stop),
            daemon=True,
        )
        scheduler_thread.start()
        log.info(
            "Autostart geplant fuer %02d:%02d",
            AUTOSTART_HOUR, AUTOSTART_MINUTE,
        )

    log.info("Wetter-Display gestartet – %s", LOCATION_NAME)
    log.info("A = %d Zyklen | A+A = Dauerbetrieb | B = Stop | X = Info | Y = Gruss", DISPLAY_CYCLES)
    log.info("Terminal: a = %d Zyklen | aa = Dauerbetrieb | b = Stop | x = Info | y = Gruss", DISPLAY_CYCLES)
    log.info("Warte auf erste Wetterdaten …")

    # Warte bis erste Daten da sind
    while not weather_data:
        time.sleep(0.5)
    log.info("Bereit.")

    # ── Main Loop ──
    while True:
        # Interrupt zurücksetzen – bereit für neuen Button-Druck
        interrupt.clear()

        # Gruss-Sequenz hat Priorität
        if greeting_requested:
            greeting_requested = False
            hat_reset(hat)
            greeting_sequence(hat, weather_data, lock)
            hat_reset(hat)
            continue

        # Info-Anzeige (Button X)
        if info_requested:
            info_requested = False
            hat_reset(hat)
            with lock:
                last_fetch = weather_data.get('_last_fetch', 0)
            if last_fetch > 0:
                fetch_time = datetime.fromtimestamp(last_fetch).strftime("%H:%M")
                age_min = int((time.time() - last_fetch) / 60)
                info_text = f"  {LOCATION_NAME}  Aktualisiert {fetch_time} (vor {age_min} min)  "
            else:
                info_text = f"  {LOCATION_NAME}  Keine Daten  "
            log.info("  [Info] %s", info_text.strip())
            hat_scroll(hat, info_text, color=(160, 160, 230))
            hat_reset(hat)
            continue

        # Idle: Display aus, kurz schlafen
        if cycles_remaining == 0:
            isleep(0.1)
            continue

        # ── Sauberer Start für neuen Zyklus ──
        hat_reset(hat)

        # ── Wetterdaten für diesen Zyklus holen ──
        with lock:
            w = weather_data.copy()

        # ── Phase 1: Icons (5 Sekunden) ──
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
        log.info("  [Phase 1] Icons")

        if not isleep(ICON_SHOW_TIME):
            log.info("  [Phase 1] UNTERBROCHEN")
            continue

        # ── Phase 2: Temperatur scrollen ──
        temp_text = (f"  Min {format_temp(w['t_min'])}°C  "
                     f"Max {format_temp(w['t_max'])}°C  ")
        log.info("  [Phase 2] Temperatur")
        if not hat_scroll(hat, temp_text, color=(220, 40, 80)):
            log.info("  [Phase 2] UNTERBROCHEN")
            continue

        if not isleep(0.5):
            continue

        # ── Phase 3: Regen scrollen ──
        regen_label = "Regen Ja" if w['regen'] else "Regen Nein"
        regen_color = (60, 60, 200) if w['regen'] else (160, 80, 200)
        log.info("  [Phase 3] %s", regen_label)
        if not hat_scroll(hat, f"  {regen_label}  ", color=regen_color):
            log.info("  [Phase 3] UNTERBROCHEN")
            continue

        if not isleep(0.5):
            continue

        # ── Phase 4: Sonne scrollen ──
        sonne_label = "Sonne Ja" if w['sonne'] else "Sonne Nein"
        sonne_color = (220, 40, 80) if w['sonne'] else (160, 80, 200)
        log.info("  [Phase 4] %s", sonne_label)
        if not hat_scroll(hat, f"  {sonne_label}  ", color=sonne_color):
            log.info("  [Phase 4] UNTERBROCHEN")
            continue

        log.info("  [Zyklus komplett]")

        # ── Zyklus-Ende ──
        if cycles_remaining > 0:
            cycles_remaining -= 1
            if cycles_remaining == 0:
                log.info("%d Zyklen abgeschlossen – Display AUS", DISPLAY_CYCLES)

        # Display zwischen Zyklen zurücksetzen
        hat_reset(hat)
        isleep(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("Beendet (KeyboardInterrupt).")
    except Exception as e:
        log.critical("Unerwarteter Fehler: %s", e, exc_info=True)
