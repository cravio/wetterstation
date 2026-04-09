"""State machine for display mode management.

Thread-safe: send_event() can be called from any thread.
process_events() must be called from the main thread only.
"""

from __future__ import annotations

import logging
import queue
from enum import Enum, auto
from typing import Any

log = logging.getLogger("wetterstation")

class DisplayState(Enum):
    """Display operating states."""

    IDLE = auto()      # Display off, waiting for input
    RUNNING = auto()   # Weather display cycle active
    GREETING = auto()  # Showing greeting sequence
    INFO = auto()      # Showing info (location + update time)
    TOMORROW = auto()  # Weather forecast for tomorrow
    TRANSIT = auto()   # Showing transit departures


class DisplayEvent(Enum):
    """Events that trigger state transitions."""

    START = auto()            # Start N cycles (kwargs: cycles=int)
    STOP = auto()             # Stop display
    SHOW_INFO = auto()        # Show info display
    SHOW_GREETING = auto()    # Show greeting sequence
    SHOW_TOMORROW = auto()    # Show tomorrow's forecast
    SHOW_TRANSIT = auto()     # Show transit departures
    CYCLE_COMPLETE = auto()   # One display cycle completed
    GREETING_COMPLETE = auto()  # Greeting sequence finished
    INFO_COMPLETE = auto()    # Info display finished
    TOMORROW_COMPLETE = auto()  # Tomorrow forecast finished
    TRANSIT_COMPLETE = auto()  # Transit display finished
    AUTOSTART = auto()        # Scheduled autostart


class StateMachine:
    """Display state machine with thread-safe event queue.

    Input threads push events via send_event().
    The main thread calls process_events() to handle transitions.
    """

    def __init__(self, interrupt: Any = None) -> None:
        self._state = DisplayState.IDLE
        self._cycles_remaining = 0
        self._interrupted = False
        self._needs_clear = False
        self._interrupt_event = interrupt  # threading.Event to abort animations
        self._event_queue: queue.Queue[tuple[DisplayEvent, dict[str, Any]]] = (
            queue.Queue()
        )

    @property
    def state(self) -> DisplayState:
        return self._state

    @property
    def cycles_remaining(self) -> int:
        return self._cycles_remaining

    @property
    def interrupted(self) -> bool:
        return self._interrupted

    @property
    def needs_clear(self) -> bool:
        return self._needs_clear

    def clear_interrupted(self) -> None:
        """Clear the interrupted flag (call from main thread after handling)."""
        self._interrupted = False

    def clear_needs_clear(self) -> None:
        """Clear the needs_clear flag (call from main thread after clearing display)."""
        self._needs_clear = False

    # Events that should immediately interrupt running animations.
    _INTERRUPTING_EVENTS = frozenset({
        DisplayEvent.START,
        DisplayEvent.STOP,
        DisplayEvent.SHOW_GREETING,
        DisplayEvent.SHOW_INFO,
        DisplayEvent.SHOW_TOMORROW,
        DisplayEvent.SHOW_TRANSIT,
        DisplayEvent.AUTOSTART,
    })

    def send_event(self, event: DisplayEvent, **kwargs: Any) -> None:
        """Thread-safe: push an event into the queue.

        Can be called from any thread (button handler, terminal, scheduler).
        For interrupting events, immediately signals running animations to abort.
        """
        self._event_queue.put((event, kwargs))
        if event in self._INTERRUPTING_EVENTS and self._interrupt_event is not None:
            self._interrupt_event.set()

    def process_events(self) -> DisplayState:
        """Process all pending events. Must be called from main thread only.

        Returns:
            Current state after processing.
        """
        while True:
            try:
                event, kwargs = self._event_queue.get_nowait()
            except queue.Empty:
                break
            self._handle_event(event, kwargs)

        return self._state

    def _set_interrupted(self) -> None:
        """Mark as interrupted and signal running animations to abort."""
        self._interrupted = True
        if self._interrupt_event is not None:
            self._interrupt_event.set()

    def _handle_event(
        self, event: DisplayEvent, kwargs: dict[str, Any]
    ) -> None:
        """Handle a single event and update state."""
        if event == DisplayEvent.START:
            cycles = kwargs.get("cycles", 10)
            self._state = DisplayState.RUNNING
            self._cycles_remaining = cycles
            self._set_interrupted()
            log.info("→ RUNNING (%d Zyklen)", cycles)

        elif event == DisplayEvent.STOP:
            self._state = DisplayState.IDLE
            self._cycles_remaining = 0
            self._set_interrupted()
            self._needs_clear = True
            log.info("→ IDLE (Stop)")

        elif event == DisplayEvent.SHOW_GREETING:
            self._state = DisplayState.GREETING
            self._set_interrupted()
            log.info("→ GREETING")

        elif event == DisplayEvent.SHOW_INFO:
            self._state = DisplayState.INFO
            self._set_interrupted()
            log.info("→ INFO")

        elif event == DisplayEvent.SHOW_TOMORROW:
            cycles = kwargs.get("cycles", 10)
            self._state = DisplayState.TOMORROW
            self._cycles_remaining = cycles
            self._set_interrupted()
            log.info("→ TOMORROW (%d Zyklen)", cycles)

        elif event == DisplayEvent.SHOW_TRANSIT:
            self._state = DisplayState.TRANSIT
            self._set_interrupted()
            log.info("→ TRANSIT")

        elif event == DisplayEvent.CYCLE_COMPLETE:
            if self._cycles_remaining > 0:
                self._cycles_remaining -= 1
                if self._cycles_remaining == 0:
                    self._state = DisplayState.IDLE
                    log.info("→ IDLE (alle Zyklen abgeschlossen)")

        elif event == DisplayEvent.GREETING_COMPLETE:
            self._state = DisplayState.IDLE
            log.info("→ IDLE (Gruss fertig)")

        elif event == DisplayEvent.INFO_COMPLETE:
            self._state = DisplayState.IDLE
            log.info("→ IDLE (Info fertig)")

        elif event == DisplayEvent.TOMORROW_COMPLETE:
            self._state = DisplayState.IDLE
            log.info("→ IDLE (Morgen fertig)")

        elif event == DisplayEvent.TRANSIT_COMPLETE:
            self._state = DisplayState.IDLE
            log.info("→ IDLE (Fahrplan fertig)")

        elif event == DisplayEvent.AUTOSTART:
            self._state = DisplayState.RUNNING
            self._cycles_remaining = kwargs.get("cycles", 10)
            self._set_interrupted()
            log.info("→ RUNNING (%s Zyklen, Autostart)", self._cycles_remaining)
