"""Tests for wetterstation.weather module."""

import pytest
import responses
from wetterstation.weather import (
    WeatherData,
    fetch_weather,
    parse_weather,
    dominant_code,
)


class TestParseWeather:
    """Test weather data parsing from API response."""

    def test_parse_returns_weather_data(self, sample_weather_api_response):
        result = parse_weather(sample_weather_api_response)
        assert isinstance(result, WeatherData)

    def test_parse_extracts_temperatures(self, sample_weather_api_response):
        result = parse_weather(sample_weather_api_response)
        assert result.t_max == 12.2
        assert result.t_min == 1.0

    def test_parse_detects_rain(self, sample_weather_api_response):
        # Sample data has rain codes (61, 63) in evening
        result = parse_weather(sample_weather_api_response)
        assert result.regen is True

    def test_parse_detects_sun(self, sample_weather_api_response):
        # Sample data has sun codes (0, 1) in morning
        result = parse_weather(sample_weather_api_response)
        assert result.sonne is True

    def test_parse_has_three_period_icons(self, sample_weather_api_response):
        result = parse_weather(sample_weather_api_response)
        assert result.morning is not None
        assert result.midday is not None
        assert result.evening is not None

    def test_parse_icons_are_5x5_grids(self, sample_weather_api_response):
        result = parse_weather(sample_weather_api_response)
        for icon in [result.morning, result.midday, result.evening]:
            assert len(icon) == 5
            for row in icon:
                assert len(row) == 5

    def test_parse_tracks_fetch_time(self, sample_weather_api_response):
        result = parse_weather(sample_weather_api_response)
        assert result.last_fetch > 0

    def test_parse_not_stale_initially(self, sample_weather_api_response):
        result = parse_weather(sample_weather_api_response)
        assert result.stale is False


class TestDominantCode:
    """Test weather code dominance calculation."""

    def test_single_code_returns_itself(self):
        times = ["2026-03-05T09:00"]
        codes = [0]
        assert dominant_code(codes, times, range(6, 12)) == 0

    def test_most_frequent_wins(self):
        times = [f"2026-03-05T{h:02d}:00" for h in range(6, 12)]
        codes = [61, 61, 61, 61, 3, 3]  # rain dominant (no sun/cloud mix)
        assert dominant_code(codes, times, range(6, 12)) == 61

    def test_sun_dominant_even_with_some_cloud(self):
        """Default (mix_sun_cloud=False): pure dominant, no partly mixing."""
        times = [f"2026-03-05T{h:02d}:00" for h in range(6, 12)]
        codes = [0, 0, 0, 3, 3, 61]  # sun most frequent
        assert dominant_code(codes, times, range(6, 12)) == 0

    def test_mixed_sun_cloud_returns_dominant_by_default(self):
        """Default: 4 cloud + 2 sun → cloud wins (most frequent)."""
        times = [f"2026-03-05T{h:02d}:00" for h in range(6, 12)]
        codes = [0, 0, 3, 3, 3, 3]  # 4 cloud, 2 sun → 3 wins
        result = dominant_code(codes, times, range(6, 12))
        assert result == 3

    def test_mix_sun_cloud_enabled_returns_partly(self):
        """With mix_sun_cloud=True: mixed sun+cloud → partly cloudy (2)."""
        times = [f"2026-03-05T{h:02d}:00" for h in range(6, 12)]
        codes = [0, 0, 3, 3, 3, 0]
        result = dominant_code(codes, times, range(6, 12), mix_sun_cloud=True)
        assert result == 2

    def test_empty_range_returns_zero(self):
        times = ["2026-03-05T09:00"]
        codes = [61]
        assert dominant_code(codes, times, range(20, 24)) == 0

    def test_only_considers_specified_hours(self):
        times = [f"2026-03-05T{h:02d}:00" for h in range(24)]
        codes = [0] * 12 + [61] * 5 + [3] * 7  # rain only in afternoon
        result = dominant_code(codes, times, range(12, 17))
        assert result == 61  # rain

    def test_rain_beats_cloud_when_more_frequent(self):
        times = [f"2026-03-05T{h:02d}:00" for h in range(6, 12)]
        codes = [61, 61, 61, 61, 3, 3]
        assert dominant_code(codes, times, range(6, 12)) == 61


class TestFetchWeather:
    """Test API fetching with retry logic."""

    @responses.activate
    def test_successful_fetch(self, sample_weather_api_response):
        responses.add(
            responses.GET,
            "https://api.open-meteo.com/v1/forecast",
            json=sample_weather_api_response,
            status=200,
        )
        result = fetch_weather(lat=47.3769, lon=8.5417)
        assert "hourly" in result
        assert "daily" in result

    @responses.activate
    def test_retry_on_failure(self, sample_weather_api_response):
        # First two attempts fail, third succeeds
        responses.add(responses.GET, "https://api.open-meteo.com/v1/forecast",
                      status=500)
        responses.add(responses.GET, "https://api.open-meteo.com/v1/forecast",
                      status=500)
        responses.add(responses.GET, "https://api.open-meteo.com/v1/forecast",
                      json=sample_weather_api_response, status=200)

        result = fetch_weather(lat=47.3769, lon=8.5417, max_retries=3,
                               retry_base_delay=0.01)
        assert "hourly" in result
        assert len(responses.calls) == 3

    @responses.activate
    def test_all_retries_fail_raises(self):
        responses.add(responses.GET, "https://api.open-meteo.com/v1/forecast",
                      status=500)
        responses.add(responses.GET, "https://api.open-meteo.com/v1/forecast",
                      status=500)
        responses.add(responses.GET, "https://api.open-meteo.com/v1/forecast",
                      status=500)

        with pytest.raises(Exception):
            fetch_weather(lat=47.3769, lon=8.5417, max_retries=3,
                          retry_base_delay=0.01)


class TestWeatherDataNoRain:
    """Test parsing when there's no rain."""

    def test_no_rain_detected(self):
        hours = [f"2026-03-05T{h:02d}:00" for h in range(24)]
        codes = [0] * 24  # all clear
        data = {
            "hourly": {"time": hours, "weathercode": codes,
                       "temperature_2m": [10.0] * 24},
            "daily": {"temperature_2m_max": [15.0], "temperature_2m_min": [5.0]},
        }
        result = parse_weather(data)
        assert result.regen is False
        assert result.sonne is True
