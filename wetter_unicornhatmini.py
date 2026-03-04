#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════╗
║   Wetter-Display – Pimoroni Unicorn HAT Mini (17×7)      ║
║   Raspberry Pi Hardware-Version                          ║
║   Voraussetzung: pip3 install unicornhatmini requests    ║
║   Starten: python3 wetter_unicornhatmini.py              ║
║                                                          ║
║   Button A = Display starten (10 Zyklen)                 ║
║   Button B = Display sofort stoppen                      ║
║   Button X = Display Dauerbetrieb                        ║
║   Button Y = Gruss-Sequenz (Herz + Text + Wetter-Icon)  ║
╚══════════════════════════════════════════════════════════╝
"""

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
    'S': ['0111','1000','0110','0001','1110'],
    'T': ['1110','0100','0100','0100','0100'],
    'W': ['1001','1001','1001','1111','0110'],
    'a': ['0000','0110','1010','1110','1001'],
    'd': ['0001','0001','0111','1001','0111'],
    'e': ['0000','0110','1110','1000','0110'],
    'g': ['0000','0111','1010','0111','0001'],
    'c': ['0000','0110','1000','1000','0110'],
    'h': ['1000','1000','1110','1001','1001'],
    'i': ['0110','0000','0110','0110','0110'],
    'l': ['0110','0010','0010','0010','0111'],
    'm': ['0000','1111','1001','1001','1001'],
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
    return max(set(vals), key=vals.count) if vals else 0

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
def hat_clear(hat):
    hat.clear()
    hat.show()

def hat_set_icon(hat, icon, x_offset):
    for row_i, row in enumerate(icon):
        for col_i, color in enumerate(row):
            hat.set_pixel(x_offset + col_i, 1 + row_i, *color)

def hat_scroll(hat, text, color=(255, 200, 0), speed=SCROLL_SPEED):
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

# ── Gruss-Sequenz (Button Y) ─────────────────────────────────────────────────
def greeting_sequence(hat, weather_data, lock):
    """3x Herz blinken → Gruss scrollen → Wetter-Icon anzeigen."""
    with lock:
        w = weather_data.copy() if weather_data else None

    if not w:
        print("Gruss: Keine Wetterdaten vorhanden.")
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
    text = f"  Hallo Carla, hallo Maura, heute wird es {t_max}°C warm"
    if w['regen']:
        text += " und es regnet"
    if w['sonne']:
        text += " und es scheint die Sonne"
    text += ". Tschuss!  "
    hat_scroll(hat, text, color=(255, 20, 80), speed=SCROLL_SPEED)

    # 3) Wetter-Icon anzeigen: Wolke bei Regen, Sonne bei kein Regen
    hat.clear()
    icon = ICON_CLOUD if w['regen'] else ICON_SUN
    hat_set_icon(hat, icon, 6)
    hat.show()
    time.sleep(4)
    hat_clear(hat)

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
    hat.set_brightness(BRIGHTNESS)
    hat_clear(hat)

    # Shared State
    weather_data = {}
    lock = threading.Lock()
    cycles_remaining = 0
    stop_event = threading.Event()
    button_override = False   # True = Button hat Zeitlogik übersteuert
    auto_started = False      # Verhindert wiederholtes Auto-Start in selber Minute

    # ── Background-Fetch starten ──
    fetch_thread = threading.Thread(
        target=weather_fetch_loop,
        args=(weather_data, lock, stop_event),
        daemon=True,
    )
    fetch_thread.start()

    # ── Buttons (Polling-Thread, kompatibel mit Pi 4 + Pi 5) ──
    BUTTON_A = 5
    BUTTON_B = 6
    BUTTON_X = 16
    BUTTON_Y = 24
    ALL_BUTTONS = (BUTTON_A, BUTTON_B, BUTTON_X, BUTTON_Y)

    for pin in ALL_BUTTONS:
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    def on_button(channel):
        nonlocal cycles_remaining, button_override
        if channel == BUTTON_A:
            cycles_remaining = DISPLAY_CYCLES
            button_override = True
            print(f"Button A → Display AN ({DISPLAY_CYCLES} Zyklen)")
        elif channel == BUTTON_B:
            cycles_remaining = 0
            button_override = True
            hat_clear(hat)
            print("Button B → Display AUS")
        elif channel == BUTTON_X:
            cycles_remaining = CONTINUOUS
            button_override = True
            print("Button X → Dauerbetrieb")
        elif channel == BUTTON_Y:
            threading.Thread(
                target=greeting_sequence,
                args=(hat, weather_data, lock),
                daemon=True,
            ).start()

    def button_poll_loop():
        """Pollt Button-States alle 50ms (kein edge detect nötig)."""
        prev = {pin: GPIO.HIGH for pin in ALL_BUTTONS}
        while True:
            for pin in ALL_BUTTONS:
                state = GPIO.input(pin)
                if state == GPIO.LOW and prev[pin] == GPIO.HIGH:
                    on_button(pin)
                prev[pin] = state
            time.sleep(0.05)

    threading.Thread(target=button_poll_loop, daemon=True).start()

    print("Wetter-Display gestartet – Zürich")
    print("A = 10 Zyklen | B = Stop | X = Dauerbetrieb | Y = Gruss")
    print(f"Auto: {AUTO_START_TIME[0]:02d}:{AUTO_START_TIME[1]:02d} Start → "
          f"{AUTO_STOP_TIME[0]:02d}:{AUTO_STOP_TIME[1]:02d} Stop")
    print("Warte auf erste Wetterdaten …")

    # Warte bis erste Daten da sind
    while not weather_data:
        time.sleep(0.5)
    print("Bereit.")

    # ── Main Loop ──
    while True:
        # ── Zeitsteuerung ──
        now = datetime.now()
        hm = (now.hour, now.minute)

        if hm == (AUTO_START_TIME[0], AUTO_START_TIME[1]):
            if not auto_started:
                if not button_override:
                    cycles_remaining = CONTINUOUS
                    print(f"[{now.strftime('%H:%M')}] Auto-Start → Dauerbetrieb")
                auto_started = True
        elif hm == (AUTO_STOP_TIME[0], AUTO_STOP_TIME[1]):
            if auto_started:
                if not button_override:
                    cycles_remaining = 0
                    hat_clear(hat)
                    print(f"[{now.strftime('%H:%M')}] Auto-Stop → Display AUS")
                auto_started = False
                button_override = False  # Reset: nächster Zeitzyklus gilt wieder
        else:
            # Ausserhalb der Schaltminuten: auto_started-Flag zurücksetzen
            if auto_started and hm > (AUTO_STOP_TIME[0], AUTO_STOP_TIME[1]):
                auto_started = False
                button_override = False

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

            if cycles_remaining == 0:
                hat_clear(hat)
                continue

            time.sleep(1)

            # Sonne scrollen
            sonne_label = "Sonne Ja" if w['sonne'] else "Sonne Nein"
            sonne_color = (220, 40, 80) if w['sonne'] else (160, 80, 200)
            hat_scroll(hat, f"  {sonne_label}  ", color=sonne_color)

            # Zyklus runterzählen (nur wenn nicht Dauerbetrieb)
            if cycles_remaining > 0:
                cycles_remaining -= 1
                if cycles_remaining == 0:
                    hat_clear(hat)
                    print("10 Zyklen abgeschlossen – Display AUS")

            time.sleep(1)
        else:
            # Display aus – idle, wenig CPU
            time.sleep(0.2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nBeendet.")
