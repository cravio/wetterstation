#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════╗
║   Wetter-Display – Pimoroni Unicorn HAT Mini (17×7)      ║
║   Raspberry Pi Hardware-Version                          ║
║   Voraussetzung: pip3 install unicornhatmini requests    ║
║   Starten: python3 wetter_unicornhatmini.py [--start]     ║
║                                                          ║
║   Button A = Display starten (10 Zyklen)                 ║
║   Button B = Display sofort stoppen                      ║
║   Button X = Display Dauerbetrieb                        ║
║   Button Y = Gruss-Sequenz (Herz + Text + Wetter-Icon)  ║
╚══════════════════════════════════════════════════════════╝
"""

import sys
import time
import threading
import requests
from datetime import datetime
from unicornhatmini import UnicornHATMini
import RPi.GPIO as GPIO

# ── Einstellungen ─────────────────────────────────────────────────────────────
SCROLL_SPEED    = 0.06
ICON_SHOW_TIME  = 5
FETCH_INTERVAL  = 30 * 60
BRIGHTNESS      = 0.4
DISPLAY_CYCLES  = 10
CONTINUOUS       = -1   # Spezieller Wert für Dauerbetrieb

# ── Zeitsteuerung (Stunde, Minute) ────────────────────────────────────────────
AUTO_START_TIME = (7, 0)    # 07:00 → Dauerbetrieb starten
AUTO_STOP_TIME  = (8, 30)   # 08:30 → Display stoppen

# ── Zürich ───────────────────────────────────────────────────────────────────
LAT, LON = 47.3769, 8.5417

# ── Farben (Berry: Rot, Lila, Blau) ──────────────────────────────────────────
OFF = (  0,   0,   0)
SUN = (220,  40,  80)   # Berry-Rot
CLO = (180, 140, 220)   # Lavendel
RAI = ( 60,  60, 200)   # Blaubeere
SNO = (210, 195, 240)   # Helles Lavendel
THU = (120,   0, 180)   # Tiefes Lila
ORG = (200,  30, 100)   # Himbeere
STR = (160, 160, 230)   # Helles Blau-Lila
GRN = (160,  80, 200)   # Mittleres Lila
HRT = (255,  20,  80)   # Herz-Rot/Pink

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
def fetch_weather():
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={LAT}&longitude={LON}"
        "&hourly=weathercode,temperature_2m"
        "&daily=temperature_2m_max,temperature_2m_min"
        "&timezone=Europe%2FZurich&forecast_days=1"
    )
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    return r.json()

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
    SUN_CODES  = {0, 1}  # Klar / Überwiegend klar

    # Ab jetziger Stunde bis 23:59
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

# ── HAT-Hilfsfunktionen ───────────────────────────────────────────────────────
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
    """Kompletter Display-Reset: Clear + Double-Show + Settle."""
    hat.clear()
    hat.show()
    time.sleep(0.005)
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

def hat_scroll(hat, text, color=(255, 200, 0), speed=SCROLL_SPEED):
    """Scrollt Text über das Display.
    Bricht sofort ab wenn interrupt gesetzt wird.
    Returns True wenn komplett, False wenn unterbrochen."""
    hat_reset(hat)
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

# ── Gruss-Sequenz (Button Y) ─────────────────────────────────────────────────
def greeting_sequence(hat, weather_data, lock):
    """3x Herz blinken → Gruss scrollen → Wetter-Icon.
    Komplett interruptible – bricht bei jedem Button-Druck sofort ab."""
    with lock:
        w = weather_data.copy() if weather_data else None

    if not w:
        print("Gruss: Keine Wetterdaten vorhanden.")
        return

    # 1) Herz 3x blinken (zentriert bei x=6)
    for _ in range(3):
        if interrupt.is_set():
            hat_reset(hat)
            return
        hat_reset(hat)
        hat_set_icon(hat, ICON_HEART, 6)
        hat.show()
        if not isleep(0.6):
            hat_reset(hat)
            return
        hat_reset(hat)
        if not isleep(0.3):
            hat_reset(hat)
            return

    # 2) Gruss-Text scrollen
    if interrupt.is_set():
        hat_reset(hat)
        return
    hat_reset(hat)
    t_max = format_temp(w['t_max'])
    text = f"  Hallo Carla, hallo Maura, heute wird es {t_max}°C warm"
    if w['regen']:
        text += " und es regnet"
    if w['sonne']:
        text += " und es scheint die Sonne"
    text += ". Tschuss!  "
    print("  [Gruss] Text scrollen", flush=True)
    if not hat_scroll(hat, text, color=(255, 20, 80), speed=SCROLL_SPEED):
        hat_reset(hat)
        return

    # 3) Wetter-Icon anzeigen
    if interrupt.is_set():
        hat_reset(hat)
        return
    hat_reset(hat)
    icon = ICON_CLOUD if w['regen'] else ICON_SUN
    hat_set_icon(hat, icon, 6)
    hat.show()
    print("  [Gruss] Wetter-Icon", flush=True)
    isleep(4)
    hat_reset(hat)

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

# ── Background Fetch Thread ──────────────────────────────────────────────────
def weather_fetch_loop(weather_data, lock, stop_event):
    """Lädt Wetterdaten alle 30 Minuten im Hintergrund."""
    while not stop_event.is_set():
        print("Lade Wetterdaten …")
        try:
            raw = fetch_weather()
            parsed = parse_weather(raw)
            with lock:
                weather_data.update(parsed)
            t = datetime.now().strftime("%H:%M")
            regen_str = "Ja" if parsed['regen'] else "Nein"
            sonne_str = "Ja" if parsed['sonne'] else "Nein"
            print(f"[{t}] Min {format_temp(parsed['t_min'])}°C / "
                  f"Max {format_temp(parsed['t_max'])}°C | "
                  f"Regen: {regen_str} | Sonne: {sonne_str}")
        except Exception as e:
            print(f"Fetch-Fehler: {e}")

        # Schlafe in kleinen Schritten, damit stop_event schnell wirkt
        for _ in range(FETCH_INTERVAL):
            if stop_event.is_set():
                return
            time.sleep(1)

# ── Hauptprogramm ─────────────────────────────────────────────────────────────
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
        print(f"--start → Display AN ({DISPLAY_CYCLES} Zyklen)")
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

    def on_button(channel):
        nonlocal cycles_remaining, button_override, greeting_requested
        # IMMER: Interrupt setzen → laufende Anzeige bricht sofort ab
        interrupt.set()

        if channel == BUTTON_A:
            cycles_remaining = DISPLAY_CYCLES
            button_override = True
            greeting_requested = False
            print(f"Button A → Display AN ({DISPLAY_CYCLES} Zyklen)", flush=True)
        elif channel == BUTTON_B:
            cycles_remaining = 0
            button_override = True
            greeting_requested = False
            print("Button B → Display AUS", flush=True)
        elif channel == BUTTON_X:
            cycles_remaining = CONTINUOUS
            button_override = True
            greeting_requested = False
            print("Button X → Dauerbetrieb", flush=True)
        elif channel == BUTTON_Y:
            cycles_remaining = 0
            greeting_requested = True
            print("Button Y → Gruss", flush=True)

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

    def stdin_loop():
        """Liest Terminal-Eingaben: r = Reset, a = Start, x = Dauerbetrieb."""
        for line in sys.stdin:
            cmd = line.strip().lower()
            if cmd == 'r':
                on_button(BUTTON_B)
                print("Terminal → Reset", flush=True)
            elif cmd == 'a':
                on_button(BUTTON_A)
            elif cmd == 'x':
                on_button(BUTTON_X)

    threading.Thread(target=stdin_loop, daemon=True).start()

    print("Wetter-Display gestartet – Zürich")
    print("A = 10 Zyklen | B = Stop | X = Dauerbetrieb | Y = Gruss")
    print("Terminal: r = Reset | a = 10 Zyklen | x = Dauerbetrieb")
    print(f"Auto: {AUTO_START_TIME[0]:02d}:{AUTO_START_TIME[1]:02d} Start → "
          f"{AUTO_STOP_TIME[0]:02d}:{AUTO_STOP_TIME[1]:02d} Stop")
    print("Warte auf erste Wetterdaten …")

    # Warte bis erste Daten da sind
    while not weather_data:
        time.sleep(0.5)
    print("Bereit.")

    def check_schedule():
        """Zeitsteuerung – wird nur im Idle aufgerufen."""
        nonlocal cycles_remaining, button_override, auto_started
        now = datetime.now()
        hm = (now.hour, now.minute)

        if hm == (AUTO_START_TIME[0], AUTO_START_TIME[1]):
            if not auto_started:
                if not button_override:
                    cycles_remaining = CONTINUOUS
                    print(f"[{now.strftime('%H:%M')}] Auto-Start → Dauerbetrieb", flush=True)
                auto_started = True
        elif hm == (AUTO_STOP_TIME[0], AUTO_STOP_TIME[1]):
            if auto_started:
                if not button_override:
                    cycles_remaining = 0
                    hat_reset(hat)
                    print(f"[{now.strftime('%H:%M')}] Auto-Stop → Display AUS", flush=True)
                auto_started = False
                button_override = False
        else:
            if auto_started and hm > (AUTO_STOP_TIME[0], AUTO_STOP_TIME[1]):
                auto_started = False
                button_override = False

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

        # Zeitsteuerung nur im Idle prüfen
        if cycles_remaining == 0:
            check_schedule()

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
        hat.show()
        print("  [Phase 1] Icons", flush=True)

        if not isleep(ICON_SHOW_TIME):
            print("  [Phase 1] UNTERBROCHEN", flush=True)
            hat_reset(hat)
            continue

        # ── Phase 2: Temperatur scrollen ──
        hat_reset(hat)
        temp_text = (f"  Min {format_temp(w['t_min'])}°C  "
                     f"Max {format_temp(w['t_max'])}°C  ")
        print("  [Phase 2] Temperatur", flush=True)
        if not hat_scroll(hat, temp_text, color=(220, 40, 80)):
            print("  [Phase 2] UNTERBROCHEN", flush=True)
            hat_reset(hat)
            continue

        # ── Phase 3: Regen scrollen ──
        hat_reset(hat)
        if not isleep(0.3):
            hat_reset(hat)
            continue
        regen_label = "Regen Ja" if w['regen'] else "Regen Nein"
        regen_color = (60, 60, 200) if w['regen'] else (160, 80, 200)
        print(f"  [Phase 3] {regen_label}", flush=True)
        if not hat_scroll(hat, f"  {regen_label}  ", color=regen_color):
            print("  [Phase 3] UNTERBROCHEN", flush=True)
            hat_reset(hat)
            continue

        # ── Phase 4: Sonne scrollen ──
        hat_reset(hat)
        if not isleep(0.3):
            hat_reset(hat)
            continue
        sonne_label = "Sonne Ja" if w['sonne'] else "Sonne Nein"
        sonne_color = (220, 40, 80) if w['sonne'] else (160, 80, 200)
        print(f"  [Phase 4] {sonne_label}", flush=True)
        if not hat_scroll(hat, f"  {sonne_label}  ", color=sonne_color):
            print("  [Phase 4] UNTERBROCHEN", flush=True)
            hat_reset(hat)
            continue

        print("  [Zyklus komplett]", flush=True)

        # ── Zyklus-Ende ──
        if cycles_remaining > 0:
            cycles_remaining -= 1
            if cycles_remaining == 0:
                print("10 Zyklen abgeschlossen – Display AUS", flush=True)

        # Display zwischen Zyklen zurücksetzen
        hat_reset(hat)
        isleep(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nBeendet.")
