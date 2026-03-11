"""Wetterstation entry point: python -m wetterstation [--start] [--simulator]

Main loop architecture:
  - All display operations happen in this thread (main thread)
  - Input threads (buttons, terminal, autostart) push events into StateMachine
  - StateMachine.process_events() is called here to handle state transitions
  - This eliminates all SPI threading issues by design
"""

from __future__ import annotations

import logging
import os
import sys
import time
import threading
from datetime import datetime

from wetterstation.config import Config, load_config
from wetterstation.state import DisplayState, DisplayEvent, StateMachine
from wetterstation.weather import WeatherData, fetch_weather, parse_weather, parse_weather_tomorrow
from wetterstation.renderer import format_temp
from wetterstation.animations import (
    weather_cycle,
    greeting_sequence,
    info_display,
)

log = logging.getLogger("wetterstation")


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def create_display(use_simulator: bool):
    """Create the display backend."""
    if use_simulator:
        from wetterstation.simulator import SimulatorBackend

        log.info("Simulator-Modus aktiv")
        return SimulatorBackend()
    else:
        from wetterstation.display import UnicornHATBackend

        return UnicornHATBackend()


def weather_fetch_loop(
    cfg: Config,
    weather_holder: list,  # [WeatherData | None]
    weather_tomorrow_holder: list,  # [WeatherData | None]
    lock: threading.Lock,
    stop_event: threading.Event,
) -> None:
    """Background thread: fetch weather data periodically."""
    while not stop_event.is_set():
        log.info("Lade Wetterdaten ...")
        try:
            raw = fetch_weather(cfg.location.lat, cfg.location.lon)
            parsed = parse_weather(raw)
            parsed_tomorrow = parse_weather_tomorrow(raw)
            with lock:
                weather_holder[0] = parsed
                weather_tomorrow_holder[0] = parsed_tomorrow
            log.info(
                "Min %s°C / Max %s°C | Regen: %s | Sonne: %s",
                format_temp(parsed.t_min),
                format_temp(parsed.t_max),
                "Ja" if parsed.regen else "Nein",
                "Ja" if parsed.sonne else "Nein",
            )
            if parsed_tomorrow:
                log.info(
                    "Morgen: Min %s°C / Max %s°C | Regen: %s | Sonne: %s",
                    format_temp(parsed_tomorrow.t_min),
                    format_temp(parsed_tomorrow.t_max),
                    "Ja" if parsed_tomorrow.regen else "Nein",
                    "Ja" if parsed_tomorrow.sonne else "Nein",
                )
        except Exception as e:
            log.error("Wetterdaten-Abruf fehlgeschlagen: %s", e)
            with lock:
                if weather_holder[0] is not None:
                    weather_holder[0].stale = True
                    age = (time.time() - weather_holder[0].last_fetch) / 60
                    log.info("Verwende letzte Daten (Alter: %d min)", age)

        for _ in range(cfg.fetch_interval):
            if stop_event.is_set():
                return
            time.sleep(1)


def autostart_scheduler(
    sm: StateMachine,
    cfg: Config,
    stop_event: threading.Event,
) -> None:
    """Background thread: activate display at configured time daily."""
    last_triggered_date = None
    while not stop_event.is_set():
        now = datetime.now()
        target_passed = (
            now.hour > cfg.autostart.hour
            or (now.hour == cfg.autostart.hour
                and now.minute >= cfg.autostart.minute)
        )
        if target_passed and last_triggered_date != now.date():
            log.info(
                "Autostart: Display aktiviert um %02d:%02d",
                cfg.autostart.hour,
                cfg.autostart.minute,
            )
            sm.send_event(DisplayEvent.AUTOSTART, cycles=cfg.display.display_cycles)
            last_triggered_date = now.date()

        for _ in range(30):
            if stop_event.is_set():
                return
            time.sleep(1)


def main() -> None:
    setup_logging()

    # ── Config ──
    config_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "config.json"
    )
    cfg = load_config(config_path)

    # ── Display ──
    use_simulator = "--simulator" in sys.argv
    display = create_display(use_simulator)
    display.set_brightness(cfg.display.brightness)
    display.clear()
    display.show()

    # ── State Machine ──
    interrupt = threading.Event()
    sm = StateMachine(interrupt=interrupt)

    if "--start" in sys.argv:
        sm.send_event(DisplayEvent.START, cycles=cfg.display.display_cycles)
        log.info("--start → %d Zyklen", cfg.display.display_cycles)

    # ── Weather Fetch Thread ──
    weather_holder: list[WeatherData | None] = [None]
    weather_tomorrow_holder: list[WeatherData | None] = [None]
    weather_lock = threading.Lock()
    stop_event = threading.Event()

    fetch_thread = threading.Thread(
        target=weather_fetch_loop,
        args=(cfg, weather_holder, weather_tomorrow_holder, weather_lock, stop_event),
        daemon=True,
    )
    fetch_thread.start()

    # ── Button Handler (only on real hardware) ──
    if not use_simulator:
        try:
            from wetterstation.input import ButtonHandler

            buttons = ButtonHandler(sm, cfg.display.display_cycles)
            buttons.start()
        except ImportError:
            log.warning("RPi.GPIO nicht verfügbar – keine Hardware-Buttons")

    # ── Terminal Input ──
    from wetterstation.input import FifoInput, TerminalInput

    terminal = TerminalInput(sm, cfg.display.display_cycles)
    terminal.start()

    # ── FIFO Remote Control ──
    fifo = FifoInput(sm, cfg.display.display_cycles)
    fifo.start()

    # ── Autostart Scheduler ──
    if cfg.autostart.enabled:
        sched_thread = threading.Thread(
            target=autostart_scheduler,
            args=(sm, cfg, stop_event),
            daemon=True,
        )
        sched_thread.start()
        log.info(
            "Autostart geplant für %02d:%02d",
            cfg.autostart.hour,
            cfg.autostart.minute,
        )

    # ── Startup Info ──
    log.info("Wetter-Display gestartet – %s", cfg.location.name)
    log.info(
        "A = %d Zyklen | A+A = Dauerbetrieb | B = Stop | X = Info | X+X = Morgen | Y = Gruss",
        cfg.display.display_cycles,
    )
    log.info(
        "Terminal: r/b = Stop | a = %d Zyklen | aa = Dauerbetrieb | x = Info | xx = Morgen | y = Gruss",
        cfg.display.display_cycles,
    )

    # Wait for first weather data
    log.info("Warte auf erste Wetterdaten ...")
    while weather_holder[0] is None:
        time.sleep(0.5)
    log.info("Bereit.")

    # ── Main Loop ──────────────────────────────────────────────────────
    # ALL display operations happen here in the main thread.
    # No other thread touches the display – ever.
    while True:
        # Process pending events from input threads
        sm.process_events()

        # Handle needs_clear (from STOP event)
        if sm.needs_clear:
            sm.clear_needs_clear()
            display.clear()
            display.show()
            time.sleep(0.01)

        # Handle interrupted (from any state change)
        if sm.interrupted:
            sm.clear_interrupted()

        # Clear interrupt AFTER processing events so animations start fresh
        interrupt.clear()

        state = sm.state

        # ── GREETING ──
        if state == DisplayState.GREETING:
            display.clear()
            display.show()
            time.sleep(0.01)

            completed = False
            with weather_lock:
                w = weather_holder[0]
            if w:
                completed = greeting_sequence(
                    display, w,
                    greeting_text=cfg.greeting_text,
                    speed=cfg.display.scroll_speed,
                    interrupt=interrupt,
                )
            display.clear()
            display.show()
            time.sleep(0.01)
            if completed or not w:
                sm.send_event(DisplayEvent.GREETING_COMPLETE)
            continue

        # ── INFO ──
        if state == DisplayState.INFO:
            display.clear()
            display.show()
            time.sleep(0.01)

            with weather_lock:
                w = weather_holder[0]
            last_fetch = w.last_fetch if w else 0

            completed = info_display(
                display,
                location=cfg.location.name,
                last_fetch=last_fetch,
                speed=cfg.display.scroll_speed,
                interrupt=interrupt,
            )
            display.clear()
            display.show()
            time.sleep(0.01)
            if completed:
                sm.send_event(DisplayEvent.INFO_COMPLETE)
            continue

        # ── IDLE ──
        if state == DisplayState.IDLE:
            time.sleep(0.1)
            continue

        # ── TOMORROW ──
        if state == DisplayState.TOMORROW:
            with weather_lock:
                w = weather_tomorrow_holder[0]
            if w is None:
                time.sleep(0.5)
                continue

            completed = weather_cycle(
                display, w,
                scroll_speed=cfg.display.scroll_speed,
                icon_time=cfg.display.icon_show_time,
                interrupt=interrupt,
            )

            if completed:
                sm.send_event(DisplayEvent.CYCLE_COMPLETE)

            display.clear()
            display.show()
            time.sleep(0.01)

            if sm.state == DisplayState.TOMORROW:
                end = time.monotonic() + 1.0
                while time.monotonic() < end:
                    if interrupt.is_set():
                        break
                    time.sleep(0.02)
            continue

        # ── RUNNING ──
        with weather_lock:
            w = weather_holder[0]
        if w is None:
            time.sleep(0.5)
            continue

        completed = weather_cycle(
            display, w,
            scroll_speed=cfg.display.scroll_speed,
            icon_time=cfg.display.icon_show_time,
            interrupt=interrupt,
        )

        if completed:
            sm.send_event(DisplayEvent.CYCLE_COMPLETE)

        # Reset display between cycles
        display.clear()
        display.show()
        time.sleep(0.01)

        # Brief pause between cycles
        if sm.state == DisplayState.RUNNING:
            end = time.monotonic() + 1.0
            while time.monotonic() < end:
                if interrupt.is_set():
                    break
                time.sleep(0.02)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("Beendet (KeyboardInterrupt).")
    except Exception as e:
        log.critical("Unerwarteter Fehler: %s", e, exc_info=True)
