"""Transit departure fetching from transport.opendata.ch API."""

from __future__ import annotations

import logging
import time
import urllib.request
import json
from dataclasses import dataclass

from wetterstation.config import TransitStationConfig

log = logging.getLogger("wetterstation")

API_URL = "https://transport.opendata.ch/v1/stationboard"


@dataclass
class TransitDeparture:
    """A single upcoming departure."""

    line: str                        # "8"
    minutes: int                     # 5
    station_short: str               # "Be"
    color: tuple[int, int, int]      # (80, 80, 255)


def fetch_departures(
    stations: list[TransitStationConfig],
) -> list[TransitDeparture]:
    """Fetch next departure per configured line per station.

    Returns departures ordered by station config order, then by minutes.
    """
    now = time.time()
    result: list[TransitDeparture] = []

    for station in stations:
        if not station.lines:
            continue

        try:
            data = _fetch_stationboard(station.id)
        except Exception as e:
            log.warning("Transit-API Fehler für %s: %s", station.short, e)
            continue

        # Track best (soonest) departure per line
        best: dict[str, TransitDeparture] = {}

        for entry in data.get("stationboard", []):
            line_num = entry.get("number", "")
            if line_num not in station.lines:
                continue

            line_cfg = station.lines[line_num]
            destination = entry.get("to", "")
            if not _matches_destination(destination, line_cfg.destinations):
                continue

            dep_ts = entry.get("stop", {}).get("departureTimestamp")
            if dep_ts is None:
                continue

            minutes = max(0, int((dep_ts - now) // 60))

            if line_num not in best or minutes < best[line_num].minutes:
                best[line_num] = TransitDeparture(
                    line=line_num,
                    minutes=minutes,
                    station_short=station.short,
                    color=line_cfg.color,
                )

        # Add in line-number order for consistent display
        for line_num in sorted(best, key=lambda x: int(x) if x.isdigit() else x):
            result.append(best[line_num])

    return result


def _matches_destination(actual: str, configured: list[str]) -> bool:
    """Check if actual destination matches any configured destination."""
    if not configured:
        return True  # no filter = accept all
    return actual in configured


def _fetch_stationboard(station_id: str) -> dict:
    """Fetch stationboard JSON from transport.opendata.ch."""
    url = f"{API_URL}?id={station_id}&limit=10"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))
