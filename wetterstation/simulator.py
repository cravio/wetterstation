"""Software simulator for the 17x7 LED display.

Used for:
- Unit testing (no hardware needed)
- Development on macOS (render=True draws the matrix in the terminal)
- Debugging animations and rendering
"""

from __future__ import annotations

import copy
import sys
from wetterstation.renderer import Color, DISPLAY_W, DISPLAY_H, OFF


class SimulatorBackend:
    """In-memory display simulator matching the DisplayBackend protocol.

    Stores pixels in a 2D array. Optionally tracks frame history
    for animation testing, or renders to the terminal via ANSI
    truecolor (render=True, used by `python -m wetterstation --simulator`).
    """

    width: int = DISPLAY_W
    height: int = DISPLAY_H

    def __init__(self, track_frames: bool = False,
                 render: bool = False) -> None:
        self._buffer: list[list[Color]] = [
            [OFF] * self.height for _ in range(self.width)
        ]
        self._track_frames = track_frames
        self._frames: list[list[list[Color]]] = []
        self._show_count = 0
        self._brightness = 0.4
        self._render = render
        self._rendered_once = False

    def set_pixel(self, x: int, y: int, r: int, g: int, b: int) -> None:
        """Set a pixel in the buffer. Out-of-bounds is silently ignored."""
        if 0 <= x < self.width and 0 <= y < self.height:
            self._buffer[x][y] = (r, g, b)

    def show(self) -> None:
        """Commit the buffer (in simulator: counter, snapshot, terminal)."""
        self._show_count += 1
        if self._track_frames:
            self._frames.append(copy.deepcopy(self._buffer))
        if self._render:
            self._render_terminal()

    def _render_terminal(self) -> None:
        """Draw the matrix in the terminal, redrawing in place."""
        out = []
        if self._rendered_once:
            out.append(f"\x1b[{self.height + 2}F")  # cursor back to frame top
        self._rendered_once = True
        border = "─" * (self.width * 2)
        out.append(f"\x1b[2K┌{border}┐\n")
        for y in range(self.height):
            row = ["\x1b[2K│"]
            for x in range(self.width):
                r, g, b = self._buffer[x][y]
                if (r, g, b) == OFF:
                    row.append("\x1b[38;2;45;45;52m██")
                else:
                    row.append(f"\x1b[38;2;{r};{g};{b}m██")
            row.append("\x1b[0m│\n")
            out.append("".join(row))
        out.append(f"\x1b[2K└{border}┘\n")
        sys.stdout.write("".join(out))
        sys.stdout.flush()

    def clear(self) -> None:
        """Clear the pixel buffer to all OFF."""
        for x in range(self.width):
            for y in range(self.height):
                self._buffer[x][y] = OFF

    def set_brightness(self, brightness: float) -> None:
        """Set brightness (clamped to 0.0–1.0)."""
        self._brightness = max(0.0, min(1.0, brightness))

    def reset(self) -> None:
        """Clear + show (matches UnicornHATBackend.reset)."""
        self.clear()
        self.show()

    # ── Test helpers ──────────────────────────────────────────────────────

    def get_pixel(self, x: int, y: int) -> Color:
        """Get pixel color at (x, y). For testing only."""
        if 0 <= x < self.width and 0 <= y < self.height:
            return self._buffer[x][y]
        return OFF

    @property
    def show_count(self) -> int:
        """Number of times show() was called."""
        return self._show_count

    @property
    def brightness(self) -> float:
        return self._brightness

    @property
    def frames(self) -> list[list[list[Color]]]:
        """Frame history (only if track_frames=True)."""
        return self._frames
