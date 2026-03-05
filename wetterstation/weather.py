"""Weather API client and data parsing for Open-Meteo."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime

import requests

from wetterstation.renderer import Icon, wmo_to_icon

log = logging.getLogger("wetterstation")


@dataclass
class WeatherData:
    """Parsed weather data for display."""

    morning: Icon     # Icon for 06:00–12:00
    midday: Icon      # Icon for 12:00–17:00
    evening: Icon     # Icon for 17:00–22:00
    t_max: float      # Max temperature °C
    t_min: float      # Min temperature °C
    regen: bool       # Rain expected today
    sonne: bool       # Sun expected today
    last_fetch: float  # time.time() of last successful fetch
    stale: bool = False  # True if data couldn't be refreshed


def fetch_weather(
    lat: float,
    lon: float,
    max_retries: int = 3,
    retry_base_delay: float = 5.0,
) -> dict:
    """Fetch weather data from Open-Meteo API with retry logic.

    Args:
        lat: Latitude.
        lon: Longitude.
        max_retries: Number of attempts before giving up.
        retry_base_delay: Base delay in seconds (exponential backoff).

    Returns:
        Raw API response as dict.

    Raises:
        requests.RequestException: If all retries fail.
    """
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&hourly=weathercode,temperature_2m"
        "&daily=temperature_2m_max,temperature_2m_min"
        "&timezone=Europe%2FZurich&forecast_days=1"
    )
    for attempt in range(max_retries):
        try:
            r = requests.get(url, timeout=15)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            wait = 2**attempt * retry_base_delay
            log.warning(
                "Fetch-Versuch %d/%d fehlgeschlagen: %s. Retry in %.1fs",
                attempt + 1,
                max_retries,
                e,
                wait,
            )
            if attempt < max_retries - 1:
                time.sleep(wait)
    raise requests.RequestException("Alle Fetch-Versuche fehlgeschlagen")


def dominant_code(
    codes: list[int],
    times: list[str],
    hour_range: range,
    mix_sun_cloud: bool = False,
) -> int:
    """Find the dominant weather code in a time range.

    Args:
        codes: List of WMO weather codes (one per hour).
        times: List of ISO time strings (one per hour).
        hour_range: Range of hours to consider.
        mix_sun_cloud: If True, return 2 (partly cloudy) when sun and
            cloud are both significantly present (>=30%).

    Returns:
        Dominant WMO weather code, or 0 if no data in range.
    """
    vals = [
        codes[i]
        for i, t in enumerate(times)
        if "T" in t and int(t.split("T")[1][:2]) in hour_range
    ]
    if not vals:
        return 0

    if mix_sun_cloud:
        code_set = set(vals)
        has_sun = bool(code_set & {0, 1})
        has_cloud = bool(code_set & {2, 3})
        if has_sun and has_cloud:
            sun_count = sum(1 for v in vals if v in (0, 1))
            cloud_count = sum(1 for v in vals if v in (2, 3))
            total = sun_count + cloud_count
            if total > 0 and min(sun_count, cloud_count) / total >= 0.3:
                return 2  # partly cloudy

    return max(set(vals), key=vals.count)


def parse_weather(data: dict) -> WeatherData:
    """Parse Open-Meteo API response into WeatherData.

    Args:
        data: Raw API response dict.

    Returns:
        Parsed WeatherData with icons, temperatures, and flags.
    """
    times = data["hourly"]["time"]
    codes = data["hourly"]["weathercode"]
    t_max = round(data["daily"]["temperature_2m_max"][0], 1)
    t_min = round(data["daily"]["temperature_2m_min"][0], 1)

    now_hour = datetime.now().hour

    RAIN_CODES = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99}
    SUN_CODES = {0, 1}

    regen = any(
        codes[i] in RAIN_CODES
        for i, t in enumerate(times)
        if "T" in t and int(t.split("T")[1][:2]) >= now_hour
    )
    sonne = any(
        codes[i] in SUN_CODES
        for i, t in enumerate(times)
        if "T" in t and int(t.split("T")[1][:2]) >= now_hour
    )

    return WeatherData(
        morning=wmo_to_icon(dominant_code(codes, times, range(6, 12)), 9),
        midday=wmo_to_icon(dominant_code(codes, times, range(12, 17)), 14),
        evening=wmo_to_icon(dominant_code(codes, times, range(17, 22)), 19),
        t_max=t_max,
        t_min=t_min,
        regen=regen,
        sonne=sonne,
        last_fetch=time.time(),
    )
