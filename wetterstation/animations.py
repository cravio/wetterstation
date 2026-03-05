"""Display animations: weather cycle, greeting, info, scrolling.

All animations are interruptible via a threading.Event.
All display access happens through the DisplayBackend protocol.
"""

from __future__ import annotations

import logging
import time
import threading
from datetime import datetime

from wetterstation.renderer import (
    Color,
    Icon,
    OFF,
    DISPLAY_W,
    DISPLAY_H,
    ICONS,
    text_to_columns,
    format_temp,
)
from wetterstation.weather import WeatherData

log = logging.getLogger("wetterstation")


def _isleep(secs: float, interrupt: threading.Event) -> bool:
    """Interruptible sleep.

    Returns True if slept fully, False if interrupted.
    """
    end = time.monotonic() + secs
    while time.monotonic() < end:
        if interrupt.is_set():
            return False
        time.sleep(0.02)
    return True


def _set_icon(display, icon: Icon, x_offset: int) -> None:
    """Draw a 5x5 icon on the display at the given x offset (y starts at 1)."""
    for row_i, row in enumerate(icon):
        for col_i, color in enumerate(row):
            display.set_pixel(x_offset + col_i, 1 + row_i, *color)


def scroll_text(
    display,
    text: str,
    color: Color,
    speed: float = 0.06,
    interrupt: threading.Event | None = None,
) -> bool:
    """Scroll text across the display.

    Args:
        display: DisplayBackend instance.
        text: Text to scroll.
        color: Text color.
        speed: Seconds per scroll step.
        interrupt: Event to check for early abort.

    Returns:
        True if completed, False if interrupted.
    """
    if interrupt is None:
        interrupt = threading.Event()

    columns = text_to_columns(text, color)
    if not columns:
        return True

    padded = ([[OFF] * DISPLAY_H] * DISPLAY_W
              + columns
              + [[OFF] * DISPLAY_H] * DISPLAY_W)

    for start in range(len(padded) - DISPLAY_W + 1):
        if interrupt.is_set():
            return False
        display.clear()
        for x in range(DISPLAY_W):
            for y in range(DISPLAY_H):
                r, g, b = padded[start + x][y]
                display.set_pixel(x, y, r, g, b)
        display.show()
        time.sleep(speed)

    return True


def show_icons(
    display,
    icons: list[Icon],
    duration: float = 5.0,
    interrupt: threading.Event | None = None,
    stale: bool = False,
) -> bool:
    """Show 3 weather icons side by side (at x=0, 6, 12).

    Args:
        display: DisplayBackend instance.
        icons: List of 3 icons [morning, midday, evening].
        duration: How long to show in seconds.
        interrupt: Event to check for early abort.
        stale: If True, show red pixel at (16, 0) as stale indicator.

    Returns:
        True if completed, False if interrupted.
    """
    if interrupt is None:
        interrupt = threading.Event()

    display.clear()
    for icon, x_off in zip(icons, [0, 6, 12]):
        _set_icon(display, icon, x_off)

    if stale:
        display.set_pixel(16, 0, 120, 0, 0)

    display.show()

    return _isleep(duration, interrupt)


def greeting_sequence(
    display,
    weather: WeatherData,
    greeting_text: str,
    speed: float = 0.06,
    interrupt: threading.Event | None = None,
    heart_blink_time: float = 0.6,
) -> bool:
    """Show greeting: 3x heart blink -> text scroll -> weather icon.

    Args:
        display: DisplayBackend instance.
        weather: Current weather data.
        greeting_text: Template string with {t_max} placeholder.
        speed: Scroll speed.
        interrupt: Event for early abort.
        heart_blink_time: Duration of each heart blink.

    Returns:
        True if completed, False if interrupted.
    """
    if interrupt is None:
        interrupt = threading.Event()

    heart = ICONS["heart"]

    # Phase 1: Heart blink 3x
    log.info("  [Gruss] Herz")
    for _ in range(3):
        if interrupt.is_set():
            return False
        display.clear()
        _set_icon(display, heart, 6)  # centered
        display.show()
        if not _isleep(heart_blink_time, interrupt):
            return False
        display.clear()
        display.show()
        if not _isleep(heart_blink_time * 0.5, interrupt):
            return False

    # Phase 2: Scroll greeting text
    if interrupt.is_set():
        return False
    t_max = format_temp(weather.t_max)
    try:
        text = f"  {greeting_text.format(t_max=t_max)}"
    except (KeyError, IndexError):
        text = f"  {greeting_text}"

    if weather.regen:
        text += " und es regnet"
    if weather.sonne:
        text += " und es scheint die Sonne"
    text += ". Tschuss!  "

    log.info("  [Gruss] Text scrollen")
    if not scroll_text(display, text, color=(255, 20, 80), speed=speed,
                       interrupt=interrupt):
        return False

    # Phase 3: Weather icon
    if interrupt.is_set():
        return False
    display.clear()
    icon = ICONS["cloud"] if weather.regen else ICONS["sun"]
    _set_icon(display, icon, 6)
    display.show()
    log.info("  [Gruss] Wetter-Icon")
    if not _isleep(4, interrupt):
        return False

    return True


def info_display(
    display,
    location: str,
    last_fetch: float,
    speed: float = 0.06,
    interrupt: threading.Event | None = None,
) -> bool:
    """Show location and last update time.

    Args:
        display: DisplayBackend instance.
        location: Location name string.
        last_fetch: Unix timestamp of last weather fetch.
        speed: Scroll speed.
        interrupt: Event for early abort.

    Returns:
        True if completed, False if interrupted.
    """
    if interrupt is None:
        interrupt = threading.Event()

    if last_fetch > 0:
        fetch_time = datetime.fromtimestamp(last_fetch).strftime("%H:%M")
        age_min = int((time.time() - last_fetch) / 60)
        info_text = f"  {location}  Aktualisiert {fetch_time} (vor {age_min} min)  "
    else:
        info_text = f"  {location}  Keine Daten  "

    log.info("  [Info] %s", info_text.strip())
    return scroll_text(display, info_text, color=(160, 160, 230), speed=speed,
                       interrupt=interrupt)


def weather_cycle(
    display,
    weather: WeatherData,
    scroll_speed: float = 0.06,
    icon_time: float = 5.0,
    interrupt: threading.Event | None = None,
) -> bool:
    """Run one complete weather display cycle.

    Phases:
    1. Show 3 weather icons (morning/midday/evening)
    2. Scroll temperature (min/max)
    3. Scroll rain status
    4. Scroll sun status

    Args:
        display: DisplayBackend instance.
        weather: Current weather data.
        scroll_speed: Text scroll speed.
        icon_time: Icon display duration.
        interrupt: Event for early abort.

    Returns:
        True if completed, False if interrupted.
    """
    if interrupt is None:
        interrupt = threading.Event()

    # Phase 1: Icons
    icons = [weather.morning, weather.midday, weather.evening]
    log.info("  [Phase 1] Icons")
    if not show_icons(display, icons, duration=icon_time, interrupt=interrupt,
                      stale=weather.stale):
        log.info("  [Phase 1] UNTERBROCHEN")
        return False

    # Phase 2: Temperature
    temp_text = (f"  Min {format_temp(weather.t_min)}°C  "
                 f"Max {format_temp(weather.t_max)}°C  ")
    log.info("  [Phase 2] Temperatur")
    if not scroll_text(display, temp_text, color=(220, 40, 80), speed=scroll_speed,
                       interrupt=interrupt):
        log.info("  [Phase 2] UNTERBROCHEN")
        return False

    if not _isleep(0.5, interrupt):
        return False

    # Phase 3: Rain
    regen_label = "Regen Ja" if weather.regen else "Regen Nein"
    regen_color = (60, 60, 200) if weather.regen else (160, 80, 200)
    log.info("  [Phase 3] %s", regen_label)
    if not scroll_text(display, f"  {regen_label}  ", color=regen_color,
                       speed=scroll_speed, interrupt=interrupt):
        log.info("  [Phase 3] UNTERBROCHEN")
        return False

    if not _isleep(0.5, interrupt):
        return False

    # Phase 4: Sun
    sonne_label = "Sonne Ja" if weather.sonne else "Sonne Nein"
    sonne_color = (220, 40, 80) if weather.sonne else (160, 80, 200)
    log.info("  [Phase 4] %s", sonne_label)
    if not scroll_text(display, f"  {sonne_label}  ", color=sonne_color,
                       speed=scroll_speed, interrupt=interrupt):
        log.info("  [Phase 4] UNTERBROCHEN")
        return False

    log.info("  [Zyklus komplett]")
    return True
