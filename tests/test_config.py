"""Tests for wetterstation.config module."""

import json
import pytest
from wetterstation.config import Config, load_config, in_quiet_hours


class TestLoadConfig:
    """Test config file loading."""

    def test_load_valid_config(self, config_file, sample_config):
        cfg = load_config(config_file)
        assert isinstance(cfg, Config)
        assert cfg.location.lat == sample_config["location"]["lat"]
        assert cfg.location.lon == sample_config["location"]["lon"]
        assert cfg.location.name == sample_config["location"]["name"]

    def test_load_missing_file_returns_defaults(self, tmp_path):
        cfg = load_config(str(tmp_path / "nonexistent.json"))
        assert isinstance(cfg, Config)
        # Should have sensible defaults
        assert cfg.location.lat == 47.3769
        assert cfg.display.brightness == 0.4

    def test_load_invalid_json_returns_defaults(self, tmp_path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{invalid json")
        cfg = load_config(str(bad_file))
        assert isinstance(cfg, Config)

    def test_load_empty_json_returns_defaults(self, tmp_path):
        empty_file = tmp_path / "empty.json"
        empty_file.write_text("{}")
        cfg = load_config(str(empty_file))
        assert isinstance(cfg, Config)
        assert cfg.display.display_cycles == 10


class TestConfigDefaults:
    """Test that all defaults are sensible."""

    def test_default_config(self):
        cfg = Config()
        assert cfg.location.lat == 47.3769
        assert cfg.location.lon == 8.5417
        assert cfg.location.name == "Zuerich"
        assert cfg.display.scroll_speed == 0.06
        assert cfg.display.icon_show_time == 5
        assert cfg.display.brightness == 0.4
        assert cfg.display.display_cycles == 10
        assert cfg.fetch_interval == 1800
        assert cfg.autostart.enabled is False
        assert cfg.autostart.hour == 7
        assert cfg.autostart.minute == 0

    def test_default_colors(self):
        cfg = Config()
        assert cfg.colors.sun == (220, 40, 80)
        assert cfg.colors.cloud == (180, 140, 220)
        assert cfg.colors.rain == (60, 60, 200)
        assert cfg.colors.heart == (255, 20, 80)


class TestConfigPartialOverride:
    """Test that partial configs merge with defaults."""

    def test_partial_location(self, tmp_path):
        f = tmp_path / "partial.json"
        f.write_text(json.dumps({"location": {"name": "Bern"}}))
        cfg = load_config(str(f))
        assert cfg.location.name == "Bern"
        # Other location fields should be defaults
        assert cfg.location.lat == 47.3769

    def test_partial_display(self, tmp_path):
        f = tmp_path / "partial.json"
        f.write_text(json.dumps({"display": {"brightness": 0.8}}))
        cfg = load_config(str(f))
        assert cfg.display.brightness == 0.8
        assert cfg.display.scroll_speed == 0.06  # default

    def test_colors_as_lists_become_tuples(self, config_file):
        cfg = load_config(config_file)
        assert isinstance(cfg.colors.sun, tuple)
        assert cfg.colors.sun == (220, 40, 80)


class TestConfigGreeting:
    """Test greeting template."""

    def test_greeting_template_with_placeholder(self, config_file):
        cfg = load_config(config_file)
        result = cfg.greeting_text.format(t_max="15")
        assert "15" in result

    def test_default_greeting_has_placeholder(self):
        cfg = Config()
        assert "{t_max}" in cfg.greeting_text

    def test_greeting_without_placeholder(self, tmp_path):
        f = tmp_path / "cfg.json"
        f.write_text(json.dumps({"greeting_text": "Einfacher Gruss"}))
        cfg = load_config(str(f))
        assert cfg.greeting_text == "Einfacher Gruss"


class TestTransitConfig:
    """Test transit configuration loading."""

    def test_no_transit_returns_none(self, tmp_path):
        f = tmp_path / "cfg.json"
        f.write_text("{}")
        cfg = load_config(str(f))
        assert cfg.transit is None

    def test_transit_loads_stations(self, tmp_path):
        f = tmp_path / "cfg.json"
        f.write_text(json.dumps({"transit": {
            "stations": [{
                "id": "8591074",
                "short": "Be",
                "lines": {
                    "8": {
                        "color": [0, 128, 255],
                        "destinations": ["Zürich, Kirche Fluntern"],
                    },
                },
            }],
            "fetch_interval": 30,
        }}))
        cfg = load_config(str(f))
        assert cfg.transit is not None
        assert len(cfg.transit.stations) == 1
        assert cfg.transit.stations[0].short == "Be"
        assert "8" in cfg.transit.stations[0].lines
        assert cfg.transit.stations[0].lines["8"].color == (0, 128, 255)
        assert cfg.transit.fetch_interval == 30

    def test_empty_transit_returns_none(self, tmp_path):
        f = tmp_path / "cfg.json"
        f.write_text(json.dumps({"transit": {"stations": []}}))
        cfg = load_config(str(f))
        assert cfg.transit is None


class TestQuietHours:
    """Test quiet-hours config + window helper."""

    def test_default_disabled(self):
        cfg = Config()
        assert cfg.quiet_hours.enabled is False
        assert cfg.quiet_hours.start == 0
        assert cfg.quiet_hours.end == 6

    def test_loads_from_sample(self, config_file):
        cfg = load_config(config_file)
        assert cfg.quiet_hours.enabled is True
        assert cfg.quiet_hours.start == 0
        assert cfg.quiet_hours.end == 6

    def test_window_simple(self):
        # 0..6: quiet at 0-5, awake at 6+
        assert in_quiet_hours(0, 0, 6) is True
        assert in_quiet_hours(3, 0, 6) is True
        assert in_quiet_hours(5, 0, 6) is True
        assert in_quiet_hours(6, 0, 6) is False
        assert in_quiet_hours(12, 0, 6) is False
        assert in_quiet_hours(23, 0, 6) is False

    def test_window_wraps_midnight(self):
        # 22..6: quiet late evening through early morning
        assert in_quiet_hours(22, 22, 6) is True
        assert in_quiet_hours(23, 22, 6) is True
        assert in_quiet_hours(0, 22, 6) is True
        assert in_quiet_hours(5, 22, 6) is True
        assert in_quiet_hours(6, 22, 6) is False
        assert in_quiet_hours(12, 22, 6) is False
        assert in_quiet_hours(21, 22, 6) is False

    def test_window_disabled_when_equal(self):
        assert in_quiet_hours(3, 0, 0) is False


class TestAirplayConfig:
    """Test airplay configuration loading."""

    def test_no_airplay_returns_none(self, tmp_path):
        f = tmp_path / "cfg.json"
        f.write_text("{}")
        cfg = load_config(str(f))
        assert cfg.airplay is None

    def test_disabled_airplay_returns_none(self, tmp_path):
        f = tmp_path / "cfg.json"
        f.write_text(json.dumps({"airplay": {"enabled": False, "fps": 30}}))
        cfg = load_config(str(f))
        assert cfg.airplay is None

    def test_airplay_loads_from_sample(self, config_file):
        cfg = load_config(config_file)
        assert cfg.airplay is not None
        assert cfg.airplay.flag_file == "/run/shairport-sync/active"
        assert cfg.airplay.capture_device == "plughw:Loopback,1,0"
        assert cfg.airplay.fps == 15
        assert cfg.airplay.peak_dot is True

    def test_airplay_partial_uses_defaults(self, tmp_path):
        f = tmp_path / "cfg.json"
        f.write_text(json.dumps({"airplay": {"enabled": True, "fps": 30}}))
        cfg = load_config(str(f))
        assert cfg.airplay is not None
        assert cfg.airplay.fps == 30
        assert cfg.airplay.floor_db == -60.0  # default
        assert cfg.airplay.attack == 0.22  # default
        assert cfg.airplay.release == 0.03  # default
        assert cfg.airplay.bands == 17  # default
        assert cfg.airplay.brightness == 0.2  # default

    def test_airplay_gradient_lists_become_tuples(self, config_file):
        cfg = load_config(config_file)
        assert all(isinstance(stop, tuple) for stop in cfg.airplay.gradient)
        assert cfg.airplay.gradient[0] == (60, 60, 200)
        assert isinstance(cfg.airplay.peak_color, tuple)
        assert cfg.airplay.peak_color == (160, 160, 230)
