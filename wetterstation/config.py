"""Configuration loading and validation for wetterstation."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field

log = logging.getLogger("wetterstation")


@dataclass
class LocationConfig:
    lat: float = 47.3769
    lon: float = 8.5417
    name: str = "Zuerich"


@dataclass
class DisplayConfig:
    scroll_speed: float = 0.06
    icon_show_time: int = 5
    brightness: float = 0.4
    display_cycles: int = 10


@dataclass
class AutostartConfig:
    enabled: bool = False
    hour: int = 7
    minute: int = 0


@dataclass
class ColorsConfig:
    sun: tuple[int, int, int] = (220, 40, 80)
    cloud: tuple[int, int, int] = (180, 140, 220)
    rain: tuple[int, int, int] = (60, 60, 200)
    snow: tuple[int, int, int] = (210, 195, 240)
    thunder: tuple[int, int, int] = (120, 0, 180)
    orange: tuple[int, int, int] = (200, 30, 100)
    star: tuple[int, int, int] = (160, 160, 230)
    green: tuple[int, int, int] = (160, 80, 200)
    heart: tuple[int, int, int] = (255, 20, 80)


@dataclass
class TransitLineConfig:
    color: tuple[int, int, int] = (255, 255, 255)
    destinations: list[str] = field(default_factory=list)


@dataclass
class TransitStationConfig:
    id: str = ""
    short: str = ""
    lines: dict[str, TransitLineConfig] = field(default_factory=dict)


@dataclass
class TransitConfig:
    stations: list[TransitStationConfig] = field(default_factory=list)
    fetch_interval: int = 60


@dataclass
class Config:
    location: LocationConfig = field(default_factory=LocationConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)
    fetch_interval: int = 1800
    greeting_text: str = "Hallo! Heute wird es {t_max}°C warm."
    autostart: AutostartConfig = field(default_factory=AutostartConfig)
    colors: ColorsConfig = field(default_factory=ColorsConfig)
    transit: TransitConfig | None = None


def _to_tuple(val: list | tuple) -> tuple[int, int, int]:
    """Convert a list or tuple to a 3-element int tuple."""
    if isinstance(val, list):
        return tuple(val)  # type: ignore[return-value]
    return val  # type: ignore[return-value]


def load_config(path: str) -> Config:
    """Load config from JSON file, falling back to defaults for missing values.

    Args:
        path: Path to config.json file.

    Returns:
        Config dataclass with all values populated.
    """
    raw: dict = {}
    try:
        with open(path) as f:
            raw = json.load(f)
    except FileNotFoundError:
        log.info("Keine config.json gefunden (%s) – verwende Standardwerte", path)
    except json.JSONDecodeError as e:
        log.warning("config.json Parse-Fehler: %s – verwende Standardwerte", e)

    # Build nested configs with partial override
    loc_raw = raw.get("location", {})
    location = LocationConfig(
        lat=loc_raw.get("lat", LocationConfig.lat),
        lon=loc_raw.get("lon", LocationConfig.lon),
        name=loc_raw.get("name", LocationConfig.name),
    )

    disp_raw = raw.get("display", {})
    display = DisplayConfig(
        scroll_speed=disp_raw.get("scroll_speed", DisplayConfig.scroll_speed),
        icon_show_time=disp_raw.get("icon_show_time", DisplayConfig.icon_show_time),
        brightness=disp_raw.get("brightness", DisplayConfig.brightness),
        display_cycles=disp_raw.get("display_cycles", DisplayConfig.display_cycles),
    )

    auto_raw = raw.get("autostart", {})
    autostart = AutostartConfig(
        enabled=auto_raw.get("enabled", AutostartConfig.enabled),
        hour=auto_raw.get("hour", AutostartConfig.hour),
        minute=auto_raw.get("minute", AutostartConfig.minute),
    )

    colors_raw = raw.get("colors", {})
    defaults = ColorsConfig()
    colors = ColorsConfig(
        sun=_to_tuple(colors_raw.get("sun", defaults.sun)),
        cloud=_to_tuple(colors_raw.get("cloud", defaults.cloud)),
        rain=_to_tuple(colors_raw.get("rain", defaults.rain)),
        snow=_to_tuple(colors_raw.get("snow", defaults.snow)),
        thunder=_to_tuple(colors_raw.get("thunder", defaults.thunder)),
        orange=_to_tuple(colors_raw.get("orange", defaults.orange)),
        star=_to_tuple(colors_raw.get("star", defaults.star)),
        green=_to_tuple(colors_raw.get("green", defaults.green)),
        heart=_to_tuple(colors_raw.get("heart", defaults.heart)),
    )

    # Transit config (optional)
    transit: TransitConfig | None = None
    transit_raw = raw.get("transit")
    if transit_raw and transit_raw.get("stations"):
        stations = []
        for s in transit_raw["stations"]:
            lines = {}
            for line_num, line_data in s.get("lines", {}).items():
                lines[line_num] = TransitLineConfig(
                    color=_to_tuple(line_data.get("color", (255, 255, 255))),
                    destinations=line_data.get("destinations", []),
                )
            stations.append(TransitStationConfig(
                id=str(s.get("id", "")),
                short=s.get("short", ""),
                lines=lines,
            ))
        transit = TransitConfig(
            stations=stations,
            fetch_interval=transit_raw.get("fetch_interval", 60),
        )

    return Config(
        location=location,
        display=display,
        fetch_interval=raw.get("fetch_interval", Config.fetch_interval),
        greeting_text=raw.get("greeting_text", Config.greeting_text),
        autostart=autostart,
        colors=colors,
        transit=transit,
    )
