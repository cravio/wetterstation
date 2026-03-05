"""Shared test fixtures for wetterstation tests."""

import json
import os
import pytest


@pytest.fixture
def sample_config() -> dict:
    """Complete sample config matching config.json structure."""
    return {
        "location": {"lat": 47.3769, "lon": 8.5417, "name": "Zuerich"},
        "display": {
            "scroll_speed": 0.06,
            "icon_show_time": 5,
            "brightness": 0.4,
            "display_cycles": 10,
        },
        "fetch_interval": 1800,
        "greeting_text": "Hallo, heute wird es {t_max} Grad warm!",
        "autostart": {"enabled": True, "hour": 7, "minute": 0},
        "colors": {
            "sun": [220, 40, 80],
            "cloud": [180, 140, 220],
            "rain": [60, 60, 200],
            "snow": [210, 195, 240],
            "thunder": [120, 0, 180],
            "orange": [200, 30, 100],
            "star": [160, 160, 230],
            "green": [160, 80, 200],
            "heart": [255, 20, 80],
        },
    }


@pytest.fixture
def config_file(tmp_path, sample_config) -> str:
    """Write sample config to a temp file, return path."""
    path = tmp_path / "config.json"
    path.write_text(json.dumps(sample_config))
    return str(path)


@pytest.fixture
def sample_weather_api_response() -> dict:
    """Realistic Open-Meteo API response for one day."""
    hours = [f"2026-03-05T{h:02d}:00" for h in range(24)]
    # Mix of weather: clear morning, clouds midday, rain evening
    codes = [0, 0, 0, 0, 0, 0,       # 00-05: clear
             1, 0, 1, 2, 2, 3,       # 06-11: partly cloudy
             3, 3, 2, 3, 3, 61,      # 12-17: cloudy then rain
             61, 63, 61, 3, 3, 0]    # 18-23: rain then clear
    temps = [2.1, 1.8, 1.5, 1.2, 1.0, 1.3,
             2.5, 4.0, 6.2, 8.1, 9.5, 10.8,
             11.5, 12.2, 12.0, 11.3, 10.1, 9.0,
             8.2, 7.5, 6.8, 5.5, 4.2, 3.1]
    return {
        "hourly": {
            "time": hours,
            "weathercode": codes,
            "temperature_2m": temps,
        },
        "daily": {
            "temperature_2m_max": [12.2],
            "temperature_2m_min": [1.0],
        },
    }
