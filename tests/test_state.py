"""Tests for wetterstation.state module."""

import pytest
from wetterstation.state import (
    DisplayState,
    DisplayEvent,
    StateMachine,
)


class TestStateMachineInit:
    """Test initial state."""

    def test_starts_idle(self):
        sm = StateMachine()
        assert sm.state == DisplayState.IDLE

    def test_no_cycles_initially(self):
        sm = StateMachine()
        assert sm.cycles_remaining == 0

    def test_not_interrupted_initially(self):
        sm = StateMachine()
        assert not sm.interrupted


class TestStartTransitions:
    """Test START event transitions."""

    def test_idle_to_running(self):
        sm = StateMachine()
        sm.send_event(DisplayEvent.START, cycles=10)
        sm.process_events()
        assert sm.state == DisplayState.RUNNING
        assert sm.cycles_remaining == 10

    def test_start_continuous(self):
        sm = StateMachine()
        sm.send_event(DisplayEvent.START_CONTINUOUS)
        sm.process_events()
        assert sm.state == DisplayState.RUNNING
        assert sm.cycles_remaining == -1  # CONTINUOUS

    def test_start_while_running_resets_cycles(self):
        sm = StateMachine()
        sm.send_event(DisplayEvent.START, cycles=10)
        sm.process_events()
        sm.send_event(DisplayEvent.START, cycles=5)
        sm.process_events()
        assert sm.state == DisplayState.RUNNING
        assert sm.cycles_remaining == 5

    def test_start_sets_interrupted(self):
        sm = StateMachine()
        sm.send_event(DisplayEvent.START, cycles=10)
        sm.process_events()
        assert sm.interrupted


class TestStopTransitions:
    """Test STOP event transitions."""

    def test_running_to_idle(self):
        sm = StateMachine()
        sm.send_event(DisplayEvent.START, cycles=10)
        sm.process_events()
        sm.send_event(DisplayEvent.STOP)
        sm.process_events()
        assert sm.state == DisplayState.IDLE
        assert sm.cycles_remaining == 0

    def test_stop_sets_interrupted(self):
        sm = StateMachine()
        sm.send_event(DisplayEvent.START, cycles=10)
        sm.process_events()
        sm.clear_interrupted()
        sm.send_event(DisplayEvent.STOP)
        sm.process_events()
        assert sm.interrupted

    def test_stop_sets_needs_clear(self):
        sm = StateMachine()
        sm.send_event(DisplayEvent.START, cycles=10)
        sm.process_events()
        sm.send_event(DisplayEvent.STOP)
        sm.process_events()
        assert sm.needs_clear

    def test_stop_while_idle_is_noop(self):
        sm = StateMachine()
        sm.send_event(DisplayEvent.STOP)
        sm.process_events()
        assert sm.state == DisplayState.IDLE

    def test_stop_cancels_greeting(self):
        sm = StateMachine()
        sm.send_event(DisplayEvent.SHOW_GREETING)
        sm.process_events()
        assert sm.state == DisplayState.GREETING
        sm.send_event(DisplayEvent.STOP)
        sm.process_events()
        assert sm.state == DisplayState.IDLE


class TestGreetingTransitions:
    """Test SHOW_GREETING event."""

    def test_idle_to_greeting(self):
        sm = StateMachine()
        sm.send_event(DisplayEvent.SHOW_GREETING)
        sm.process_events()
        assert sm.state == DisplayState.GREETING

    def test_running_to_greeting(self):
        sm = StateMachine()
        sm.send_event(DisplayEvent.START, cycles=10)
        sm.process_events()
        sm.send_event(DisplayEvent.SHOW_GREETING)
        sm.process_events()
        assert sm.state == DisplayState.GREETING

    def test_greeting_sets_interrupted(self):
        sm = StateMachine()
        sm.send_event(DisplayEvent.SHOW_GREETING)
        sm.process_events()
        assert sm.interrupted

    def test_greeting_complete_returns_to_idle(self):
        sm = StateMachine()
        sm.send_event(DisplayEvent.SHOW_GREETING)
        sm.process_events()
        sm.send_event(DisplayEvent.GREETING_COMPLETE)
        sm.process_events()
        assert sm.state == DisplayState.IDLE


class TestInfoTransitions:
    """Test SHOW_INFO event."""

    def test_idle_to_info(self):
        sm = StateMachine()
        sm.send_event(DisplayEvent.SHOW_INFO)
        sm.process_events()
        assert sm.state == DisplayState.INFO

    def test_running_to_info(self):
        sm = StateMachine()
        sm.send_event(DisplayEvent.START, cycles=10)
        sm.process_events()
        sm.send_event(DisplayEvent.SHOW_INFO)
        sm.process_events()
        assert sm.state == DisplayState.INFO

    def test_info_complete_returns_to_idle(self):
        sm = StateMachine()
        sm.send_event(DisplayEvent.SHOW_INFO)
        sm.process_events()
        sm.send_event(DisplayEvent.INFO_COMPLETE)
        sm.process_events()
        assert sm.state == DisplayState.IDLE


class TestCycleComplete:
    """Test CYCLE_COMPLETE event."""

    def test_decrements_cycles(self):
        sm = StateMachine()
        sm.send_event(DisplayEvent.START, cycles=3)
        sm.process_events()
        sm.send_event(DisplayEvent.CYCLE_COMPLETE)
        sm.process_events()
        assert sm.cycles_remaining == 2

    def test_last_cycle_transitions_to_idle(self):
        sm = StateMachine()
        sm.send_event(DisplayEvent.START, cycles=1)
        sm.process_events()
        sm.send_event(DisplayEvent.CYCLE_COMPLETE)
        sm.process_events()
        assert sm.state == DisplayState.IDLE
        assert sm.cycles_remaining == 0

    def test_continuous_never_decrements(self):
        sm = StateMachine()
        sm.send_event(DisplayEvent.START_CONTINUOUS)
        sm.process_events()
        for _ in range(100):
            sm.send_event(DisplayEvent.CYCLE_COMPLETE)
            sm.process_events()
        assert sm.state == DisplayState.RUNNING
        assert sm.cycles_remaining == -1


class TestAutostart:
    """Test AUTOSTART event."""

    def test_autostart_uses_configured_cycles(self):
        sm = StateMachine()
        sm.send_event(DisplayEvent.AUTOSTART, cycles=10)
        sm.process_events()
        assert sm.state == DisplayState.RUNNING
        assert sm.cycles_remaining == 10

    def test_autostart_default_cycles(self):
        sm = StateMachine()
        sm.send_event(DisplayEvent.AUTOSTART)
        sm.process_events()
        assert sm.state == DisplayState.RUNNING
        assert sm.cycles_remaining == 10


class TestMultipleEvents:
    """Test multiple events in sequence."""

    def test_rapid_start_stop(self):
        sm = StateMachine()
        sm.send_event(DisplayEvent.START, cycles=10)
        sm.send_event(DisplayEvent.STOP)
        sm.process_events()
        assert sm.state == DisplayState.IDLE

    def test_start_greeting_stop(self):
        sm = StateMachine()
        sm.send_event(DisplayEvent.START, cycles=10)
        sm.send_event(DisplayEvent.SHOW_GREETING)
        sm.send_event(DisplayEvent.STOP)
        sm.process_events()
        assert sm.state == DisplayState.IDLE

    def test_process_events_is_idempotent(self):
        sm = StateMachine()
        sm.send_event(DisplayEvent.START, cycles=10)
        sm.process_events()
        sm.process_events()  # no events, should be no-op
        assert sm.state == DisplayState.RUNNING
        assert sm.cycles_remaining == 10


class TestClearInterrupted:
    """Test interrupt flag management."""

    def test_clear_interrupted(self):
        sm = StateMachine()
        sm.send_event(DisplayEvent.START, cycles=10)
        sm.process_events()
        assert sm.interrupted
        sm.clear_interrupted()
        assert not sm.interrupted

    def test_clear_needs_clear(self):
        sm = StateMachine()
        sm.send_event(DisplayEvent.START, cycles=10)
        sm.process_events()
        sm.send_event(DisplayEvent.STOP)
        sm.process_events()
        assert sm.needs_clear
        sm.clear_needs_clear()
        assert not sm.needs_clear
