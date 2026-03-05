"""Tests for wetterstation.display and wetterstation.simulator modules."""

import pytest
from wetterstation.simulator import SimulatorBackend


class TestSimulatorBackend:
    """Test the simulator display backend."""

    def test_dimensions(self):
        display = SimulatorBackend()
        assert display.width == 17
        assert display.height == 7

    def test_initial_pixels_are_off(self):
        display = SimulatorBackend()
        for x in range(display.width):
            for y in range(display.height):
                assert display.get_pixel(x, y) == (0, 0, 0)

    def test_set_pixel(self):
        display = SimulatorBackend()
        display.set_pixel(5, 3, 255, 0, 0)
        assert display.get_pixel(5, 3) == (255, 0, 0)

    def test_set_pixel_does_not_affect_neighbors(self):
        display = SimulatorBackend()
        display.set_pixel(5, 3, 255, 0, 0)
        assert display.get_pixel(4, 3) == (0, 0, 0)
        assert display.get_pixel(6, 3) == (0, 0, 0)
        assert display.get_pixel(5, 2) == (0, 0, 0)
        assert display.get_pixel(5, 4) == (0, 0, 0)

    def test_clear_resets_all_pixels(self):
        display = SimulatorBackend()
        display.set_pixel(5, 3, 255, 0, 0)
        display.set_pixel(10, 5, 0, 255, 0)
        display.clear()
        display.show()
        for x in range(display.width):
            for y in range(display.height):
                assert display.get_pixel(x, y) == (0, 0, 0)

    def test_show_commits_buffer(self):
        """show() makes buffered changes visible."""
        display = SimulatorBackend()
        display.set_pixel(0, 0, 255, 0, 0)
        display.show()
        assert display.get_pixel(0, 0) == (255, 0, 0)

    def test_set_brightness(self):
        display = SimulatorBackend()
        display.set_brightness(0.5)
        assert display.brightness == 0.5

    def test_brightness_clamp(self):
        display = SimulatorBackend()
        display.set_brightness(1.5)
        assert display.brightness == 1.0
        display.set_brightness(-0.5)
        assert display.brightness == 0.0

    def test_out_of_bounds_pixel_ignored(self):
        display = SimulatorBackend()
        # Should not raise
        display.set_pixel(17, 0, 255, 0, 0)
        display.set_pixel(0, 7, 255, 0, 0)
        display.set_pixel(-1, 0, 255, 0, 0)

    def test_show_count_tracked(self):
        display = SimulatorBackend()
        assert display.show_count == 0
        display.show()
        assert display.show_count == 1
        display.show()
        assert display.show_count == 2

    def test_frame_history(self):
        """Simulator tracks frames for animation testing."""
        display = SimulatorBackend(track_frames=True)
        display.set_pixel(0, 0, 255, 0, 0)
        display.show()
        display.set_pixel(0, 0, 0, 255, 0)
        display.show()
        assert len(display.frames) == 2
        assert display.frames[0][0][0] == (255, 0, 0)
        assert display.frames[1][0][0] == (0, 255, 0)


class TestDisplayProtocol:
    """Test that SimulatorBackend satisfies the DisplayBackend protocol."""

    def test_has_required_attributes(self):
        display = SimulatorBackend()
        assert hasattr(display, "width")
        assert hasattr(display, "height")

    def test_has_required_methods(self):
        display = SimulatorBackend()
        assert callable(display.set_pixel)
        assert callable(display.show)
        assert callable(display.clear)
        assert callable(display.set_brightness)
