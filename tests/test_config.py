"""Tests for wetterstation.config module."""

import json
import pytest
from wetterstation.config import Config, load_config


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
