"""Input handling: hardware buttons, terminal commands, and FIFO remote control.

All handlers push DisplayEvents into the StateMachine queue.
None of them touches the display directly – that's the main thread's job.
"""

from __future__ import annotations

import logging
import os
import sys
import time
import threading
from typing import TYPE_CHECKING

from wetterstation.state import DisplayEvent

if TYPE_CHECKING:
    from wetterstation.state import StateMachine

log = logging.getLogger("wetterstation")


def dispatch_command(
    cmd: str,
    sm: StateMachine,
    display_cycles: int,
    source: str = "Terminal",
) -> None:
    """Dispatch a text command to the state machine.

    Shared by TerminalInput and FifoInput.
    """
    if cmd in ("r", "b"):
        sm.send_event(DisplayEvent.STOP)
        log.info("%s → Stop", source)
    elif cmd == "aa":
        sm.send_event(DisplayEvent.START_CONTINUOUS)
        log.info("%s → Dauerbetrieb", source)
    elif cmd == "a":
        sm.send_event(DisplayEvent.START, cycles=display_cycles)
        log.info("%s → %d Zyklen", source, display_cycles)
    elif cmd == "xx":
        sm.send_event(DisplayEvent.SHOW_TOMORROW, cycles=display_cycles)
        log.info("%s → Morgen (%d Zyklen)", source, display_cycles)
    elif cmd == "x":
        sm.send_event(DisplayEvent.SHOW_INFO)
        log.info("%s → Info", source)
    elif cmd == "y":
        sm.send_event(DisplayEvent.SHOW_GREETING)
        log.info("%s → Gruss", source)


class ButtonHandler:
    """GPIO button handler with double-click detection for Buttons A and X.

    Buttons (BCM pins):
      A (5): single = start N cycles, double = continuous
      B (6): stop
      X (16): single = show info, double = tomorrow forecast
      Y (24): show greeting

    Runs a polling loop in a daemon thread.
    """

    BUTTON_A = 5
    BUTTON_B = 6
    BUTTON_X = 16
    BUTTON_Y = 24
    ALL_BUTTONS = (BUTTON_A, BUTTON_B, BUTTON_X, BUTTON_Y)
    DOUBLE_CLICK_WINDOW = 3.0
    POLL_INTERVAL = 0.05

    def __init__(self, state_machine: StateMachine, display_cycles: int = 10) -> None:
        self._sm = state_machine
        self._display_cycles = display_cycles
        self._last_a_press = 0.0
        self._a_click_timer: threading.Timer | None = None
        self._last_x_press = 0.0
        self._x_click_timer: threading.Timer | None = None

    def start(self) -> None:
        """Initialize GPIO and start polling thread."""
        import RPi.GPIO as GPIO

        for pin in self.ALL_BUTTONS:
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        thread = threading.Thread(target=self._poll_loop, daemon=True)
        thread.start()
        log.info("Button-Handler gestartet (GPIO-Polling)")

    def _poll_loop(self) -> None:
        """Poll button states every 50ms."""
        import RPi.GPIO as GPIO

        prev = {pin: 1 for pin in self.ALL_BUTTONS}
        while True:
            for pin in self.ALL_BUTTONS:
                state = GPIO.input(pin)
                if state == 0 and prev[pin] == 1:  # falling edge
                    self._on_button(pin)
                prev[pin] = state
            time.sleep(self.POLL_INTERVAL)

    def _on_button(self, pin: int) -> None:
        """Dispatch button press to handler."""
        if pin == self.BUTTON_A:
            self._on_a()
        elif pin == self.BUTTON_B:
            self._sm.send_event(DisplayEvent.STOP)
            log.info("Button B → Stop")
        elif pin == self.BUTTON_X:
            self._on_x()
        elif pin == self.BUTTON_Y:
            self._sm.send_event(DisplayEvent.SHOW_GREETING)
            log.info("Button Y → Gruss")

    def _on_a(self) -> None:
        """Handle Button A with double-click detection."""
        now = time.monotonic()
        elapsed = now - self._last_a_press
        self._last_a_press = now

        if elapsed <= self.DOUBLE_CLICK_WINDOW:
            # Double-click: cancel pending single-click, start continuous
            if self._a_click_timer is not None:
                self._a_click_timer.cancel()
                self._a_click_timer = None
            self._sm.send_event(DisplayEvent.START_CONTINUOUS)
            log.info("Button A Doppelklick → Dauerbetrieb")
        else:
            # First click: start timer, wait for possible second
            if self._a_click_timer is not None:
                self._a_click_timer.cancel()
            self._a_click_timer = threading.Timer(
                self.DOUBLE_CLICK_WINDOW, self._on_a_single
            )
            self._a_click_timer.daemon = True
            self._a_click_timer.start()

    def _on_a_single(self) -> None:
        """Called after double-click window expires → single click confirmed."""
        self._sm.send_event(DisplayEvent.START, cycles=self._display_cycles)
        log.info("Button A → %d Zyklen", self._display_cycles)

    def _on_x(self) -> None:
        """Handle Button X with double-click detection."""
        now = time.monotonic()
        elapsed = now - self._last_x_press
        self._last_x_press = now

        if elapsed <= self.DOUBLE_CLICK_WINDOW:
            if self._x_click_timer is not None:
                self._x_click_timer.cancel()
                self._x_click_timer = None
            self._sm.send_event(DisplayEvent.SHOW_TOMORROW, cycles=self._display_cycles)
            log.info("Button X Doppelklick → Morgen (%d Zyklen)", self._display_cycles)
        else:
            if self._x_click_timer is not None:
                self._x_click_timer.cancel()
            self._x_click_timer = threading.Timer(
                self.DOUBLE_CLICK_WINDOW, self._on_x_single
            )
            self._x_click_timer.daemon = True
            self._x_click_timer.start()

    def _on_x_single(self) -> None:
        """Called after double-click window expires → single click confirmed."""
        self._sm.send_event(DisplayEvent.SHOW_INFO)
        log.info("Button X → Info")


class TerminalInput:
    """Terminal command handler reading from stdin.

    Commands:
      a   = start N cycles
      aa  = continuous mode
      b/r = stop
      x   = info
      y   = greeting
    """

    def __init__(self, state_machine: StateMachine, display_cycles: int = 10) -> None:
        self._sm = state_machine
        self._display_cycles = display_cycles

    def start(self) -> None:
        """Start stdin reading thread."""
        thread = threading.Thread(target=self._read_loop, daemon=True)
        thread.start()
        log.info("Terminal-Input gestartet")

    def _read_loop(self) -> None:
        """Read commands from stdin."""
        for line in sys.stdin:
            cmd = line.strip().lower()
            dispatch_command(cmd, self._sm, self._display_cycles, "Terminal")


class FifoInput:
    """Named pipe (FIFO) command handler for remote control.

    Allows sending commands when running as a systemd service (no stdin).

    Usage from another terminal or SSH:
        echo a > /tmp/wetterstation.cmd
        echo b > /tmp/wetterstation.cmd

    Commands: same as TerminalInput (a, aa, b/r, x, y).
    """

    FIFO_PATH = "/tmp/wetterstation.cmd"

    def __init__(self, state_machine: StateMachine, display_cycles: int = 10) -> None:
        self._sm = state_machine
        self._display_cycles = display_cycles

    def start(self) -> None:
        """Create FIFO and start reading thread."""
        thread = threading.Thread(target=self._read_loop, daemon=True)
        thread.start()
        log.info("FIFO-Input gestartet (%s)", self.FIFO_PATH)

    def _read_loop(self) -> None:
        """Read commands from named pipe (re-opens after each writer disconnects)."""
        # Create FIFO (remove stale one first)
        try:
            if os.path.exists(self.FIFO_PATH):
                os.remove(self.FIFO_PATH)
            os.mkfifo(self.FIFO_PATH)
            os.chmod(self.FIFO_PATH, 0o666)
        except OSError as e:
            log.error("FIFO erstellen fehlgeschlagen: %s", e)
            return

        while True:
            try:
                # open() blocks until a writer connects
                with open(self.FIFO_PATH, "r") as fifo:
                    for line in fifo:
                        cmd = line.strip().lower()
                        if cmd:
                            dispatch_command(
                                cmd, self._sm, self._display_cycles, "FIFO"
                            )
            except OSError as e:
                log.warning("FIFO Lesefehler: %s", e)
                time.sleep(1)
