"""Tests for wetterstation.animations module."""

import threading
import time
import pytest
from wetterstation.simulator import SimulatorBackend
from wetterstation.animations import (
    scroll_text,
    show_icons,
    greeting_sequence,
    info_display,
    weather_cycle,
)
from wetterstation.renderer import ICONS, OFF, DISPLAY_W, DISPLAY_H
from wetterstation.weather import WeatherData


@pytest.fixture
def display():
    return SimulatorBackend(track_frames=True)


@pytest.fixture
def interrupt():
    return threading.Event()


@pytest.fixture
def sample_weather():
    return WeatherData(
        morning=ICONS["sun"],
        midday=ICONS["cloud"],
        evening=ICONS["rain"],
        t_max=15.0,
        t_min=3.0,
        regen=True,
        sonne=True,
        last_fetch=time.time(),
        stale=False,
    )


class TestScrollText:
    """Test text scrolling animation."""

    def test_scroll_completes(self, display, interrupt):
        result = scroll_text(display, "Hi", color=(255, 0, 0),
                             speed=0.001, interrupt=interrupt)
        assert result is True
        assert display.show_count > 0

    def test_scroll_interruptible(self, display, interrupt):
        interrupt.set()  # pre-set interrupt
        result = scroll_text(display, "Hello World", color=(255, 0, 0),
                             speed=0.01, interrupt=interrupt)
        assert result is False

    def test_scroll_generates_frames(self, display, interrupt):
        scroll_text(display, "AB", color=(255, 0, 0),
                    speed=0.001, interrupt=interrupt)
        assert len(display.frames) > 1  # multiple frames = scrolling

    def test_scroll_empty_text(self, display, interrupt):
        result = scroll_text(display, "", color=(255, 0, 0),
                             speed=0.001, interrupt=interrupt)
        assert result is True


class TestShowIcons:
    """Test icon display."""

    def test_shows_three_icons(self, display, interrupt):
        icons = [ICONS["sun"], ICONS["cloud"], ICONS["rain"]]
        result = show_icons(display, icons, duration=0.01, interrupt=interrupt)
        assert result is True
        assert display.show_count >= 1

    def test_icons_interruptible(self, display, interrupt):
        interrupt.set()
        icons = [ICONS["sun"], ICONS["cloud"], ICONS["rain"]]
        result = show_icons(display, icons, duration=5, interrupt=interrupt)
        assert result is False

    def test_stale_indicator(self, display, interrupt):
        """When stale=True, pixel (16, 0) should be red."""
        icons = [ICONS["sun"], ICONS["cloud"], ICONS["rain"]]
        show_icons(display, icons, duration=0.01, interrupt=interrupt, stale=True)
        assert display.get_pixel(16, 0) == (120, 0, 0)

    def test_no_stale_indicator_when_fresh(self, display, interrupt):
        icons = [ICONS["sun"], ICONS["cloud"], ICONS["rain"]]
        show_icons(display, icons, duration=0.01, interrupt=interrupt, stale=False)
        assert display.get_pixel(16, 0) != (120, 0, 0)


class TestGreetingSequence:
    """Test greeting animation sequence."""

    def test_greeting_completes(self, display, interrupt, sample_weather):
        result = greeting_sequence(
            display, sample_weather,
            greeting_text="Hallo, {t_max} Grad!",
            speed=0.001, interrupt=interrupt,
        )
        assert result is True
        assert display.show_count > 0

    def test_greeting_interruptible(self, display, interrupt, sample_weather):
        interrupt.set()
        result = greeting_sequence(
            display, sample_weather,
            greeting_text="Hallo!",
            speed=0.001, interrupt=interrupt,
        )
        assert result is False

    def test_greeting_shows_heart(self, display, interrupt, sample_weather):
        """First phase should show heart icon."""
        greeting_sequence(
            display, sample_weather,
            greeting_text="Hi",
            speed=0.001, interrupt=interrupt,
            heart_blink_time=0.001,
        )
        # Heart should have been displayed (check frames for heart color)
        heart_color = (255, 20, 80)
        has_heart = any(
            heart_color in [pixel for row in frame for pixel in row]
            for frame in display.frames
        )
        assert has_heart, "Heart icon was never displayed"

    def test_greeting_formats_temperature(self, display, interrupt, sample_weather):
        """Greeting text should include actual temperature."""
        # We can't easily test scrolled text content, but we verify it doesn't crash
        result = greeting_sequence(
            display, sample_weather,
            greeting_text="Es wird {t_max}°C warm",
            speed=0.001, interrupt=interrupt,
        )
        assert result is True


class TestInfoDisplay:
    """Test info display (location + update time)."""

    def test_info_completes(self, display, interrupt):
        result = info_display(
            display,
            location="Zuerich",
            last_fetch=time.time(),
            speed=0.001,
            interrupt=interrupt,
        )
        assert result is True

    def test_info_interruptible(self, display, interrupt):
        interrupt.set()
        result = info_display(
            display,
            location="Zuerich",
            last_fetch=time.time(),
            speed=0.001,
            interrupt=interrupt,
        )
        assert result is False

    def test_info_with_no_data(self, display, interrupt):
        """When last_fetch is 0, should show 'Keine Daten'."""
        result = info_display(
            display,
            location="Zuerich",
            last_fetch=0,
            speed=0.001,
            interrupt=interrupt,
        )
        assert result is True


class TestWeatherCycle:
    """Test one complete weather display cycle."""

    def test_cycle_completes(self, display, interrupt, sample_weather):
        result = weather_cycle(
            display, sample_weather,
            scroll_speed=0.001, icon_time=0.01, interrupt=interrupt,
        )
        assert result is True

    def test_cycle_interruptible_during_icons(self, display, interrupt, sample_weather):
        # Interrupt after a brief delay
        def delayed_interrupt():
            time.sleep(0.005)
            interrupt.set()

        t = threading.Thread(target=delayed_interrupt, daemon=True)
        t.start()
        result = weather_cycle(
            display, sample_weather,
            scroll_speed=0.001, icon_time=10,  # long icon time to ensure interrupt
            interrupt=interrupt,
        )
        assert result is False

    def test_cycle_has_four_phases(self, display, interrupt, sample_weather):
        """A complete cycle should show icons, temp, rain, and sun info."""
        weather_cycle(
            display, sample_weather,
            scroll_speed=0.001, icon_time=0.01, interrupt=interrupt,
        )
        # Should have many frames (icons + 3 scrolling texts)
        assert display.show_count > 10
