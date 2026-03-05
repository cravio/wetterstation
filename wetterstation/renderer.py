"""Font, icons, and text rendering for the 17x7 LED display.

All functions are pure – no hardware dependency.
"""

from __future__ import annotations

from typing import TypeAlias

# ── Types ────────────────────────────────────────────────────────────────────
Color: TypeAlias = tuple[int, int, int]
Icon: TypeAlias = list[list[Color]]

DISPLAY_W = 17
DISPLAY_H = 7

OFF: Color = (0, 0, 0)

# ── Default Colors ───────────────────────────────────────────────────────────
SUN: Color = (220, 40, 80)
CLO: Color = (180, 140, 220)
RAI: Color = (60, 60, 200)
SNO: Color = (210, 195, 240)
THU: Color = (120, 0, 180)
ORG: Color = (200, 30, 100)
STR: Color = (160, 160, 230)
GRN: Color = (160, 80, 200)
HRT: Color = (255, 20, 80)

# ── Icons (5 rows × 5 cols) ─────────────────────────────────────────────────
ICONS: dict[str, Icon] = {
    "sun": [
        [SUN, OFF, SUN, OFF, SUN],
        [OFF, SUN, SUN, SUN, OFF],
        [SUN, SUN, SUN, SUN, SUN],
        [OFF, SUN, SUN, SUN, OFF],
        [SUN, OFF, SUN, OFF, SUN],
    ],
    "cloud": [
        [OFF, OFF, CLO, OFF, OFF],
        [OFF, CLO, CLO, CLO, OFF],
        [CLO, CLO, CLO, CLO, CLO],
        [CLO, CLO, CLO, CLO, CLO],
        [OFF, OFF, OFF, OFF, OFF],
    ],
    "partly": [
        [OFF, OFF, SUN, OFF, OFF],
        [OFF, SUN, CLO, CLO, OFF],
        [SUN, CLO, CLO, CLO, CLO],
        [OFF, CLO, CLO, CLO, CLO],
        [OFF, OFF, OFF, OFF, OFF],
    ],
    "rain": [
        [OFF, CLO, CLO, CLO, OFF],
        [CLO, CLO, CLO, CLO, CLO],
        [OFF, OFF, OFF, OFF, OFF],
        [RAI, OFF, RAI, OFF, RAI],
        [OFF, RAI, OFF, RAI, OFF],
    ],
    "drizzle": [
        [OFF, CLO, CLO, CLO, OFF],
        [CLO, CLO, CLO, CLO, CLO],
        [OFF, OFF, OFF, OFF, OFF],
        [OFF, STR, OFF, STR, OFF],
        [OFF, OFF, OFF, OFF, OFF],
    ],
    "snow": [
        [OFF, CLO, CLO, CLO, OFF],
        [CLO, CLO, CLO, CLO, CLO],
        [OFF, OFF, OFF, OFF, OFF],
        [SNO, OFF, SNO, OFF, SNO],
        [OFF, SNO, OFF, SNO, OFF],
    ],
    "thunder": [
        [OFF, CLO, CLO, CLO, OFF],
        [CLO, CLO, CLO, CLO, CLO],
        [OFF, OFF, THU, THU, OFF],
        [OFF, THU, THU, OFF, OFF],
        [OFF, OFF, OFF, THU, OFF],
    ],
    "night": [
        [OFF, OFF, SUN, SUN, OFF],
        [OFF, SUN, OFF, OFF, OFF],
        [OFF, SUN, OFF, OFF, OFF],
        [OFF, SUN, OFF, OFF, OFF],
        [OFF, OFF, SUN, SUN, OFF],
    ],
    "fog": [
        [OFF, OFF, OFF, OFF, OFF],
        [CLO, CLO, CLO, CLO, CLO],
        [OFF, OFF, OFF, OFF, OFF],
        [OFF, CLO, CLO, CLO, OFF],
        [CLO, CLO, CLO, CLO, CLO],
    ],
    "heart": [
        [OFF, HRT, OFF, HRT, OFF],
        [HRT, HRT, HRT, HRT, HRT],
        [HRT, HRT, HRT, HRT, HRT],
        [OFF, HRT, HRT, HRT, OFF],
        [OFF, OFF, HRT, OFF, OFF],
    ],
}

# ── Font (4 wide × 5 tall bitmaps) ──────────────────────────────────────────
FONT: dict[str, list[str]] = {
    "0": ["0110", "1001", "1001", "1001", "0110"],
    "1": ["0100", "1100", "0100", "0100", "1110"],
    "2": ["0110", "1001", "0010", "0100", "1111"],
    "3": ["1110", "0001", "0110", "0001", "1110"],
    "4": ["1010", "1010", "1111", "0010", "0010"],
    "5": ["1111", "1000", "1110", "0001", "1110"],
    "6": ["0110", "1000", "1110", "1001", "0110"],
    "7": ["1111", "0001", "0010", "0100", "0100"],
    "8": ["0110", "1001", "0110", "1001", "0110"],
    "9": ["0110", "1001", "0111", "0001", "0110"],
    ".": ["0000", "0000", "0000", "0000", "0100"],
    ",": ["0000", "0000", "0000", "0100", "1000"],
    "-": ["0000", "0000", "1110", "0000", "0000"],
    "!": ["0100", "0100", "0100", "0000", "0100"],
    "?": ["0110", "1001", "0010", "0000", "0010"],
    " ": ["0000", "0000", "0000", "0000", "0000"],
    "°": ["0110", "0110", "0000", "0000", "0000"],
    ":": ["0000", "0100", "0000", "0100", "0000"],
    "(": ["0010", "0100", "0100", "0100", "0010"],
    ")": ["0100", "0010", "0010", "0010", "0100"],
    # Uppercase
    "A": ["0110", "1001", "1111", "1001", "1001"],
    "B": ["1110", "1001", "1110", "1001", "1110"],
    "C": ["0110", "1000", "1000", "1000", "0110"],
    "D": ["1100", "1010", "1001", "1010", "1100"],
    "E": ["1111", "1000", "1110", "1000", "1111"],
    "F": ["1111", "1000", "1110", "1000", "1000"],
    "G": ["0110", "1000", "1011", "1001", "0110"],
    "H": ["1001", "1001", "1111", "1001", "1001"],
    "I": ["1110", "0100", "0100", "0100", "1110"],
    "J": ["0011", "0001", "0001", "1001", "0110"],
    "K": ["1001", "1010", "1100", "1010", "1001"],
    "L": ["1000", "1000", "1000", "1000", "1111"],
    "M": ["1001", "1111", "1111", "1001", "1001"],
    "N": ["1001", "1101", "1011", "1001", "1001"],
    "O": ["0110", "1001", "1001", "1001", "0110"],
    "P": ["1110", "1001", "1110", "1000", "1000"],
    "Q": ["0110", "1001", "1001", "1010", "0101"],
    "R": ["1110", "1001", "1110", "1010", "1001"],
    "S": ["0110", "1000", "0110", "0001", "0110"],
    "T": ["1110", "0100", "0100", "0100", "0100"],
    "U": ["1001", "1001", "1001", "1001", "0110"],
    "V": ["1001", "1001", "1001", "0110", "0110"],
    "W": ["1001", "1001", "1001", "1111", "0110"],
    "X": ["1001", "1001", "0110", "1001", "1001"],
    "Y": ["1001", "1001", "0110", "0100", "0100"],
    "Z": ["1111", "0001", "0110", "1000", "1111"],
    # Lowercase
    "a": ["0000", "0110", "0010", "1010", "0111"],
    "b": ["1000", "1000", "1110", "1001", "1110"],
    "c": ["0000", "0110", "1000", "1000", "0110"],
    "d": ["0001", "0001", "0111", "1001", "0111"],
    "e": ["0000", "0110", "1111", "1000", "0110"],
    "f": ["0010", "0100", "1110", "0100", "0100"],
    "g": ["0000", "0111", "1001", "0111", "0110"],
    "h": ["1000", "1000", "1110", "1001", "1001"],
    "i": ["0100", "0000", "0100", "0100", "0100"],
    "j": ["0010", "0000", "0010", "0010", "0100"],
    "k": ["1000", "1010", "1100", "1010", "1001"],
    "l": ["1100", "0100", "0100", "0100", "1110"],
    "m": ["0000", "1111", "1001", "1001", "1001"],
    "n": ["0000", "1110", "1001", "1001", "1001"],
    "o": ["0000", "0110", "1001", "1001", "0110"],
    "p": ["0000", "1110", "1001", "1110", "1000"],
    "q": ["0000", "0111", "1001", "0111", "0001"],
    "r": ["0000", "1011", "1100", "1000", "1000"],
    "s": ["0000", "0110", "1100", "0011", "1110"],
    "t": ["0100", "1110", "0100", "0100", "0011"],
    "u": ["0000", "1001", "1001", "1001", "0110"],
    "v": ["0000", "1001", "1001", "0110", "0110"],
    "w": ["0000", "1001", "1001", "1111", "0110"],
    "x": ["0000", "1001", "0110", "0110", "1001"],
    "y": ["0000", "1001", "0111", "0001", "0110"],
    "z": ["0000", "1111", "0010", "0100", "1111"],
}


def text_to_columns(text: str, color: Color) -> list[list[Color]]:
    """Render text string to pixel columns for scrolling.

    Each character produces 4 pixel columns + 1 spacer column.
    Each column is DISPLAY_H pixels tall, with the glyph vertically
    centered (1px offset from top).

    Args:
        text: String to render.
        color: Foreground color for lit pixels.

    Returns:
        List of columns, each column is a list of DISPLAY_H Color tuples.
    """
    if not text:
        return []

    columns: list[list[Color]] = []
    y_offset = 1  # 1px from top for vertical centering on 7-high display

    for char in text:
        bitmap = FONT.get(char, FONT[" "])
        for col in range(4):
            col_pixels: list[Color] = []
            for row in range(DISPLAY_H):
                if row < y_offset or row >= y_offset + 5:
                    col_pixels.append(OFF)
                else:
                    fr = row - y_offset
                    col_pixels.append(color if bitmap[fr][col] == "1" else OFF)
            columns.append(col_pixels)
        # Spacer column between characters
        columns.append([OFF] * DISPLAY_H)

    return columns


def format_temp(value: float) -> str:
    """Format temperature: '15' for integers, '15.5' for decimals."""
    if value == int(value):
        return str(int(value))
    return str(value)


def wmo_to_icon(code: int, hour: int) -> Icon:
    """Map WMO weather code + hour to an icon.

    Args:
        code: WMO weather code (0-99).
        hour: Hour of day (0-23), used for day/night distinction.

    Returns:
        5x5 icon grid.
    """
    if code == 0:
        return ICONS["sun"] if 6 <= hour < 20 else ICONS["night"]
    elif code in (1, 2):
        return ICONS["partly"]
    elif code == 3:
        return ICONS["cloud"]
    elif code in (45, 48):
        return ICONS["fog"]
    elif code in (51, 53, 55, 56, 57):
        return ICONS["drizzle"]
    elif code in (61, 63, 65, 66, 67, 80, 81, 82):
        return ICONS["rain"]
    elif code in (71, 73, 75, 77, 85, 86):
        return ICONS["snow"]
    elif code in (95, 96, 99):
        return ICONS["thunder"]
    else:
        return ICONS["cloud"]
