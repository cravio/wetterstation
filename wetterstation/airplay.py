"""AirPlay stream detection via shairport-sync flag file.

shairport-sync sessioncontrol hooks touch/remove a flag file in
/run/shairport-sync/ (cleaned up by systemd RuntimeDirectory when the
service stops). This watcher polls the file and translates edges into
AIRPLAY_START / AIRPLAY_STOP events.

Level-triggered by design: at startup the current file state is sent as
an initial event, so a wetterstation restart mid-stream resyncs.
"""

from __future__ import annotations

import logging
import os
import threading

from wetterstation.state import DisplayEvent, StateMachine

log = logging.getLogger("wetterstation")


class AirplayWatcher:
    """Daemon thread: poll the flag file, push events on edges."""

    def __init__(
        self,
        sm: StateMachine,
        flag_path: str,
        poll_interval: float = 1.0,
    ) -> None:
        self._sm = sm
        self._flag_path = flag_path
        self._poll_interval = poll_interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        # Initial resync: report current state unconditionally
        active = os.path.exists(self._flag_path)
        if active:
            log.info("AirPlay-Stream beim Start aktiv (Resync)")
            self._sm.send_event(DisplayEvent.AIRPLAY_START)

        while not self._stop.wait(self._poll_interval):
            now_active = os.path.exists(self._flag_path)
            if now_active and not active:
                self._sm.send_event(DisplayEvent.AIRPLAY_START)
            elif not now_active and active:
                self._sm.send_event(DisplayEvent.AIRPLAY_STOP)
            active = now_active
