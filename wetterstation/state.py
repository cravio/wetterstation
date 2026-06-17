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

    IDLE = auto()       # Display off, waiting for input
    RUNNING = auto()    # Weather display cycle active
    GREETING = auto()   # Showing greeting sequence
    INFO = auto()       # Showing info (location + update time)
    TOMORROW = auto()   # Weather forecast for tomorrow
    TRANSIT = auto()    # Showing transit departures
    AUDIO_VIZ = auto()  # Audio spectrum visualizer (AirPlay streaming)


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
    AIRPLAY_START = auto()    # AirPlay stream became active
    AIRPLAY_STOP = auto()     # AirPlay stream ended
    TOGGLE_VIZ = auto()       # Manually show/hide the visualizer (button Y)
    QUIET_ON = auto()         # Enter night mode (display dark, no autostart)
    QUIET_OFF = auto()        # Leave night mode


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
        self._airplay_active = False
        self._viz_suppressed = False
        self._viz_manual = False
        self._quiet_mode = False
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

    @property
    def airplay_active(self) -> bool:
        return self._airplay_active

    @property
    def viz_suppressed(self) -> bool:
        return self._viz_suppressed

    @property
    def viz_manual(self) -> bool:
        return self._viz_manual

    @property
    def viz_wanted(self) -> bool:
        """Whether the audio analyzer should run (stream active or manual)."""
        return self._airplay_active or self._viz_manual

    @property
    def quiet_mode(self) -> bool:
        return self._quiet_mode

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
        DisplayEvent.AIRPLAY_STOP,
        DisplayEvent.TOGGLE_VIZ,
        DisplayEvent.QUIET_ON,
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

    def _idle_or_viz(self) -> DisplayState:
        """Where to go when a display finishes: visualizer if AirPlay
        streams or it was turned on manually (and not suppressed by a
        button press), else idle."""
        if (self._airplay_active or self._viz_manual) and not self._viz_suppressed:
            return DisplayState.AUDIO_VIZ
        return DisplayState.IDLE

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
            if self._state == DisplayState.AUDIO_VIZ:
                # Button press during visualizer: dark until next session
                self._viz_suppressed = True
                self._state = DisplayState.IDLE
            else:
                self._state = self._idle_or_viz()
            self._cycles_remaining = 0
            self._set_interrupted()
            self._needs_clear = True
            log.info("→ %s (Stop)", self._state.name)

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
                    self._state = self._idle_or_viz()
                    log.info("→ %s (alle Zyklen abgeschlossen)", self._state.name)

        elif event == DisplayEvent.GREETING_COMPLETE:
            self._state = self._idle_or_viz()
            log.info("→ %s (Gruss fertig)", self._state.name)

        elif event == DisplayEvent.INFO_COMPLETE:
            self._state = self._idle_or_viz()
            log.info("→ %s (Info fertig)", self._state.name)

        elif event == DisplayEvent.TOMORROW_COMPLETE:
            self._state = self._idle_or_viz()
            log.info("→ %s (Morgen fertig)", self._state.name)

        elif event == DisplayEvent.TRANSIT_COMPLETE:
            self._state = self._idle_or_viz()
            log.info("→ %s (Fahrplan fertig)", self._state.name)

        elif event == DisplayEvent.AUTOSTART:
            if self._quiet_mode:
                log.info("Autostart unterdrückt (Nachtruhe)")
            else:
                self._state = DisplayState.RUNNING
                self._cycles_remaining = kwargs.get("cycles", 10)
                self._set_interrupted()
                log.info("→ RUNNING (%s Zyklen, Autostart)",
                         self._cycles_remaining)

        elif event == DisplayEvent.AIRPLAY_START:
            self._airplay_active = True
            self._viz_suppressed = False  # new session resets suppression
            if self._state == DisplayState.IDLE:
                self._state = DisplayState.AUDIO_VIZ
                self._set_interrupted()
                log.info("→ AUDIO_VIZ (AirPlay aktiv)")
            else:
                log.info("AirPlay aktiv (Anzeige hat Vorrang)")

        elif event == DisplayEvent.AIRPLAY_STOP:
            self._airplay_active = False
            # A manually-toggled visualizer keeps running when the stream ends.
            if self._state == DisplayState.AUDIO_VIZ and not self._viz_manual:
                self._state = DisplayState.IDLE
                self._set_interrupted()
                self._needs_clear = True
                log.info("→ IDLE (AirPlay beendet)")
            else:
                log.info("AirPlay beendet")

        elif event == DisplayEvent.QUIET_ON:
            self._quiet_mode = True
            # Turn any weather-type display dark; never kill the music viz.
            if self._state not in (DisplayState.IDLE, DisplayState.AUDIO_VIZ):
                self._state = DisplayState.IDLE
                self._cycles_remaining = 0
                self._set_interrupted()
                self._needs_clear = True
            log.info("→ Nachtruhe aktiv (%s)", self._state.name)

        elif event == DisplayEvent.QUIET_OFF:
            self._quiet_mode = False
            log.info("Nachtruhe beendet")

        elif event == DisplayEvent.TOGGLE_VIZ:
            if self._state == DisplayState.AUDIO_VIZ:
                self._viz_manual = False
                self._state = DisplayState.IDLE
                self._set_interrupted()
                self._needs_clear = True
                log.info("→ IDLE (Visualizer aus)")
            else:
                self._viz_manual = True
                self._viz_suppressed = False
                self._state = DisplayState.AUDIO_VIZ
                self._set_interrupted()
                log.info("→ AUDIO_VIZ (Visualizer an)")
