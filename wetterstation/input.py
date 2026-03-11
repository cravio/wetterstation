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
    if cmd in ("r", "s"):
        sm.send_event(DisplayEvent.STOP)
        log.info("%s → Stop", source)
    elif cmd == "a":
        sm.send_event(DisplayEvent.START, cycles=display_cycles)
        log.info("%s → %d Zyklen", source, display_cycles)
    elif cmd == "b":
        sm.send_event(DisplayEvent.SHOW_TOMORROW, cycles=display_cycles)
        log.info("%s → Morgen (%d Zyklen)", source, display_cycles)
    elif cmd == "x":
        sm.send_event(DisplayEvent.START_CONTINUOUS)
        log.info("%s → Dauerbetrieb", source)
    elif cmd == "y":
        sm.send_event(DisplayEvent.SHOW_GREETING)
        log.info("%s → Gruss", source)


class ButtonHandler:
    """GPIO button handler with toggle behavior.

    Any button press while the display is active stops and clears first.
    When idle, each button starts its action:
      A (5): 10 cycles today
      B (6): 10 cycles tomorrow
      X (16): continuous today
      Y (24): greeting

    Runs a polling loop in a daemon thread.
    """

    BUTTON_A = 5
    BUTTON_B = 6
    BUTTON_X = 16
    BUTTON_Y = 24
    ALL_BUTTONS = (BUTTON_A, BUTTON_B, BUTTON_X, BUTTON_Y)
    POLL_INTERVAL = 0.05

    def __init__(self, state_machine: StateMachine, display_cycles: int = 10) -> None:
        self._sm = state_machine
        self._display_cycles = display_cycles

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

    def _is_active(self) -> bool:
        """Check if display is currently showing something."""
        from wetterstation.state import DisplayState
        return self._sm.state != DisplayState.IDLE

    def _on_button(self, pin: int) -> None:
        """Dispatch button press: stop if active, otherwise start action."""
        if self._is_active():
            self._sm.send_event(DisplayEvent.STOP)
            log.info("Button %s → Stop (war aktiv)", self._pin_name(pin))
            return

        if pin == self.BUTTON_A:
            self._sm.send_event(DisplayEvent.START, cycles=self._display_cycles)
            log.info("Button A → %d Zyklen", self._display_cycles)
        elif pin == self.BUTTON_B:
            self._sm.send_event(DisplayEvent.SHOW_TOMORROW, cycles=self._display_cycles)
            log.info("Button B → Morgen (%d Zyklen)", self._display_cycles)
        elif pin == self.BUTTON_X:
            self._sm.send_event(DisplayEvent.START_CONTINUOUS)
            log.info("Button X → Dauerbetrieb")
        elif pin == self.BUTTON_Y:
            self._sm.send_event(DisplayEvent.SHOW_GREETING)
            log.info("Button Y → Gruss")

    @staticmethod
    def _pin_name(pin: int) -> str:
        names = {5: "A", 6: "B", 16: "X", 24: "Y"}
        return names.get(pin, str(pin))


class TerminalInput:
    """Terminal command handler reading from stdin.

    Commands:
      a   = 10 cycles today
      b   = 10 cycles tomorrow
      x   = continuous today
      y   = greeting
      r/s = stop
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

    Commands: same as TerminalInput (a, b, x, y, r/s).
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
