"""Tests for wetterstation.renderer module."""

import pytest
from wetterstation.renderer import (
    FONT,
    ICONS,
    Color,
    text_to_columns,
    format_temp,
    wmo_to_icon,
    DISPLAY_W,
    DISPLAY_H,
    OFF,
)


class TestFont:
    """Test font completeness and structure."""

    REQUIRED_CHARS = set(
        "0123456789"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "abcdefghijklmnopqrstuvwxyz"
        " .,-!°:()?"
    )

    def test_font_has_all_required_characters(self):
        missing = self.REQUIRED_CHARS - set(FONT.keys())
        assert not missing, f"Font missing characters: {missing}"

    def test_font_glyphs_are_5_rows(self):
        for char, glyph in FONT.items():
            assert len(glyph) == 5, f"Font char '{char}' has {len(glyph)} rows, expected 5"

    def test_font_glyphs_are_4_wide(self):
        for char, glyph in FONT.items():
            for row_idx, row in enumerate(glyph):
                assert len(row) == 4, (
                    f"Font char '{char}' row {row_idx} is {len(row)} wide, expected 4"
                )

    def test_font_glyphs_contain_only_0_and_1(self):
        for char, glyph in FONT.items():
            for row in glyph:
                assert all(c in "01" for c in row), (
                    f"Font char '{char}' contains invalid pixel: {row}"
                )

    def test_space_is_blank(self):
        assert FONT[" "] == ["0000", "0000", "0000", "0000", "0000"]

    def test_info_text_chars_exist(self):
        """Characters needed for info display: 'Aktualisiert 12:34 (vor 5 min)'"""
        needed = set("Aktualisiert 12:34 (vor 5 min)")
        missing = needed - set(FONT.keys())
        assert not missing, f"Info text missing chars: {missing}"

    def test_greeting_text_chars_exist(self):
        """Characters needed for greeting: 'Hallo Carla, hallo Maura, heute wird es 15°C warm'"""
        needed = set("Hallo Carla, hallo Maura, heute wird es 15°C warm. Tschuss!")
        missing = needed - set(FONT.keys())
        assert not missing, f"Greeting text missing chars: {missing}"

    def test_weather_text_chars_exist(self):
        """Characters needed for weather display: 'Min 5°C Max 15°C Regen Ja Sonne Nein'"""
        needed = set("Min 5°C Max 15°C Regen Ja Sonne Nein-.")
        missing = needed - set(FONT.keys())
        assert not missing, f"Weather text missing chars: {missing}"


class TestTextToColumns:
    """Test text rendering to pixel columns."""

    def test_empty_string_returns_empty(self):
        cols = text_to_columns("", color=(255, 255, 255))
        assert cols == []

    def test_single_space_returns_5_columns(self):
        # 4 pixel columns + 1 spacer = 5 columns per char
        cols = text_to_columns(" ", color=(255, 255, 255))
        assert len(cols) == 5

    def test_column_height_matches_display(self):
        cols = text_to_columns("A", color=(255, 0, 0))
        for col in cols:
            assert len(col) == DISPLAY_H

    def test_foreground_color_applied(self):
        fg = (255, 0, 0)
        cols = text_to_columns("1", color=fg)
        # '1' starts with '0100' - second pixel should be fg
        # columns[0] = first pixel column of char '1'
        has_fg = any(fg in col for col in cols)
        assert has_fg, "Foreground color not found in rendered text"

    def test_background_is_off(self):
        cols = text_to_columns("1", color=(255, 0, 0))
        # Should have OFF pixels where font has '0'
        has_off = any(OFF in col for col in cols)
        assert has_off

    def test_two_chars_are_wider_than_one(self):
        one = text_to_columns("A", color=(255, 255, 255))
        two = text_to_columns("AB", color=(255, 255, 255))
        assert len(two) > len(one)

    def test_chars_are_5_columns_wide(self):
        """Each character = 4 pixel columns + 1 spacer = 5 total."""
        one = text_to_columns("A", color=(255, 255, 255))
        two = text_to_columns("AB", color=(255, 255, 255))
        assert len(two) - len(one) == 5  # second char adds 5 columns


class TestFormatTemp:
    """Test temperature formatting."""

    def test_integer_temp_no_decimal(self):
        assert format_temp(15.0) == "15"

    def test_negative_integer(self):
        assert format_temp(-3.0) == "-3"

    def test_decimal_temp_kept(self):
        assert format_temp(15.5) == "15.5"

    def test_zero(self):
        assert format_temp(0.0) == "0"

    def test_negative_decimal(self):
        assert format_temp(-2.3) == "-2.3"


class TestIcons:
    """Test icon definitions."""

    EXPECTED_ICONS = [
        "sun", "cloud", "partly", "rain", "drizzle",
        "snow", "thunder", "night", "fog", "heart",
    ]

    def test_all_expected_icons_exist(self):
        for name in self.EXPECTED_ICONS:
            assert name in ICONS, f"Icon '{name}' missing"

    def test_icons_are_5x5(self):
        for name, icon in ICONS.items():
            assert len(icon) == 5, f"Icon '{name}' has {len(icon)} rows, expected 5"
            for row_idx, row in enumerate(icon):
                assert len(row) == 5, (
                    f"Icon '{name}' row {row_idx} has {len(row)} cols, expected 5"
                )

    def test_icon_pixels_are_color_tuples(self):
        for name, icon in ICONS.items():
            for row in icon:
                for pixel in row:
                    assert isinstance(pixel, tuple) and len(pixel) == 3, (
                        f"Icon '{name}' has invalid pixel: {pixel}"
                    )


class TestWmoToIcon:
    """Test WMO weather code to icon mapping."""

    def test_clear_day_returns_sun(self):
        icon = wmo_to_icon(0, hour=12)
        assert icon == ICONS["sun"]

    def test_clear_night_returns_night(self):
        icon = wmo_to_icon(0, hour=22)
        assert icon == ICONS["night"]

    def test_partly_cloudy(self):
        icon = wmo_to_icon(2, hour=12)
        assert icon == ICONS["partly"]

    def test_overcast_returns_cloud(self):
        icon = wmo_to_icon(3, hour=12)
        assert icon == ICONS["cloud"]

    def test_rain_codes(self):
        for code in [61, 63, 65, 80, 81, 82]:
            icon = wmo_to_icon(code, hour=12)
            assert icon == ICONS["rain"], f"Code {code} should map to rain"

    def test_drizzle_codes(self):
        for code in [51, 53, 55]:
            icon = wmo_to_icon(code, hour=12)
            assert icon == ICONS["drizzle"], f"Code {code} should map to drizzle"

    def test_snow_codes(self):
        for code in [71, 73, 75, 77, 85, 86]:
            icon = wmo_to_icon(code, hour=12)
            assert icon == ICONS["snow"], f"Code {code} should map to snow"

    def test_thunder_codes(self):
        for code in [95, 96, 99]:
            icon = wmo_to_icon(code, hour=12)
            assert icon == ICONS["thunder"], f"Code {code} should map to thunder"

    def test_fog_codes(self):
        for code in [45, 48]:
            icon = wmo_to_icon(code, hour=12)
            assert icon == ICONS["fog"], f"Code {code} should map to fog"

    def test_unknown_code_returns_cloud(self):
        icon = wmo_to_icon(999, hour=12)
        assert icon == ICONS["cloud"]

    def test_night_boundary_6am(self):
        assert wmo_to_icon(0, hour=6) == ICONS["sun"]  # 6:00 = day

    def test_night_boundary_20pm(self):
        assert wmo_to_icon(0, hour=20) == ICONS["night"]  # 20:00 = night
