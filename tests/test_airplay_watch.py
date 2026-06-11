"""Tests for wetterstation.airplay: flag file watcher."""

import time

from wetterstation.airplay import AirplayWatcher
from wetterstation.state import DisplayEvent, DisplayState, StateMachine


def wait_for(predicate, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class TestAirplayWatcher:
    def test_initial_resync_when_flag_exists(self, tmp_path):
        flag = tmp_path / "active"
        flag.touch()
        sm = StateMachine()
        watcher = AirplayWatcher(sm, str(flag), poll_interval=0.02)
        watcher.start()
        try:
            assert wait_for(
                lambda: sm.process_events() == DisplayState.AUDIO_VIZ
            )
            assert sm.airplay_active
        finally:
            watcher.stop()

    def test_no_event_when_flag_absent(self, tmp_path):
        flag = tmp_path / "active"
        sm = StateMachine()
        watcher = AirplayWatcher(sm, str(flag), poll_interval=0.02)
        watcher.start()
        try:
            time.sleep(0.1)
            assert sm.process_events() == DisplayState.IDLE
            assert not sm.airplay_active
        finally:
            watcher.stop()

    def test_start_event_on_rising_edge(self, tmp_path):
        flag = tmp_path / "active"
        sm = StateMachine()
        watcher = AirplayWatcher(sm, str(flag), poll_interval=0.02)
        watcher.start()
        try:
            time.sleep(0.05)
            flag.touch()
            assert wait_for(
                lambda: sm.process_events() == DisplayState.AUDIO_VIZ
            )
        finally:
            watcher.stop()

    def test_stop_event_on_falling_edge(self, tmp_path):
        flag = tmp_path / "active"
        flag.touch()
        sm = StateMachine()
        watcher = AirplayWatcher(sm, str(flag), poll_interval=0.02)
        watcher.start()
        try:
            assert wait_for(
                lambda: sm.process_events() == DisplayState.AUDIO_VIZ
            )
            flag.unlink()
            assert wait_for(
                lambda: sm.process_events() == DisplayState.IDLE
            )
            assert not sm.airplay_active
        finally:
            watcher.stop()

    def test_no_duplicate_events_without_edge(self, tmp_path):
        flag = tmp_path / "active"
        flag.touch()
        sm = StateMachine()
        watcher = AirplayWatcher(sm, str(flag), poll_interval=0.02)
        watcher.start()
        try:
            assert wait_for(lambda: sm.airplay_active or
                            sm.process_events() == DisplayState.AUDIO_VIZ)
            # Suppress viz via STOP; with no further edges the watcher
            # must not re-trigger AUDIO_VIZ
            sm.send_event(DisplayEvent.STOP)
            sm.process_events()
            time.sleep(0.1)
            assert sm.process_events() == DisplayState.IDLE
        finally:
            watcher.stop()
