"""Display backend protocol and UnicornHAT Mini implementation.

The Protocol defines the interface. SimulatorBackend (in simulator.py)
implements it for testing. UnicornHATBackend implements it for real hardware.
"""

from __future__ import annotations

import logging
import time
from typing import Protocol, runtime_checkable

log = logging.getLogger("wetterstation")


@runtime_checkable
class DisplayBackend(Protocol):
    """Protocol for display backends (HAT hardware or simulator)."""

    width: int
    height: int

    def set_pixel(self, x: int, y: int, r: int, g: int, b: int) -> None:
        """Set a pixel in the buffer (does NOT trigger SPI/display update)."""
        ...

    def show(self) -> None:
        """Push the buffer to the physical display."""
        ...

    def clear(self) -> None:
        """Clear the pixel buffer (does NOT push to display)."""
        ...

    def set_brightness(self, brightness: float) -> None:
        """Set display brightness (0.0 to 1.0)."""
        ...


class UnicornHATBackend:
    """Real hardware backend for Pimoroni Unicorn HAT Mini.

    Includes Pi 5 SPI stability fixes:
    - Paced xfer: 1ms minimum between SPI transfers
    - Double-show: each show() sends data twice with 2ms gap
    """

    width: int = 17
    height: int = 7

    def __init__(self) -> None:
        from unicornhatmini import UnicornHATMini

        self._hat = UnicornHATMini()
        self._patch_spi()
        log.info("UnicornHAT Mini initialisiert (Pi 5 SPI-Fix aktiv)")

    def _patch_spi(self) -> None:
        """Pi 5 SPI-Fix: xfer-Pacing (1ms) + Double-Show."""
        original_xfer = self._hat.xfer
        original_show = self._hat.show
        last_xfer = [0.0]

        def paced_xfer(device, pin, command):
            elapsed = time.monotonic() - last_xfer[0]
            if elapsed < 0.001:
                time.sleep(0.001 - elapsed)
            original_xfer(device, pin, command)
            last_xfer[0] = time.monotonic()

        def stable_show():
            original_show()
            time.sleep(0.002)
            original_show()

        self._hat.xfer = paced_xfer
        self._hat.show = stable_show

    def set_pixel(self, x: int, y: int, r: int, g: int, b: int) -> None:
        self._hat.set_pixel(x, y, r, g, b)

    def show(self) -> None:
        self._hat.show()

    def clear(self) -> None:
        self._hat.clear()

    def set_brightness(self, brightness: float) -> None:
        self._hat.set_brightness(brightness)

    def reset(self) -> None:
        """Clear + show + settle. Call from main thread only."""
        self._hat.clear()
        self._hat.show()
        time.sleep(0.01)
