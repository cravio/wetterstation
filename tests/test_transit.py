"""Tests for transit departure fetching and parsing."""

from __future__ import annotations

import time

from wetterstation.config import TransitLineConfig, TransitStationConfig
from wetterstation.transit import (
    TransitDeparture,
    fetch_departures,
    _matches_destination,
    _fetch_stationboard,
)


def _make_entry(number: str, to: str, minutes_from_now: int) -> dict:
    """Build a fake stationboard entry."""
    ts = int(time.time()) + minutes_from_now * 60
    return {
        "number": number,
        "to": to,
        "stop": {
            "departureTimestamp": ts,
        },
    }


def _make_station(
    station_id: str = "123",
    short: str = "Te",
    lines: dict | None = None,
) -> TransitStationConfig:
    if lines is None:
        lines = {
            "8": TransitLineConfig(
                color=(0, 128, 255),
                destinations=["Zürich, Kirche Fluntern"],
            ),
        }
    return TransitStationConfig(id=station_id, short=short, lines=lines)


def _make_api_response(entries: list[dict]) -> dict:
    return {"stationboard": entries}


class TestMatchesDestination:
    def test_empty_config_matches_all(self):
        assert _matches_destination("Anywhere", []) is True

    def test_exact_match(self):
        assert _matches_destination("Zürich, Seebach", ["Zürich, Seebach"]) is True

    def test_no_match(self):
        assert _matches_destination("Zürich, Hardturm", ["Zürich, Seebach"]) is False

    def test_multiple_destinations(self):
        dests = ["Zürich, Seebach", "Zürich Oerlikon, Bahnhof"]
        assert _matches_destination("Zürich Oerlikon, Bahnhof", dests) is True


class TestFetchDepartures:
    def test_filters_by_line(self, monkeypatch):
        entries = [
            _make_entry("8", "Zürich, Kirche Fluntern", 5),
            _make_entry("99", "Zürich, Nirgendwo", 3),
        ]
        monkeypatch.setattr(
            "wetterstation.transit._fetch_stationboard",
            lambda sid: _make_api_response(entries),
        )

        station = _make_station()
        result = fetch_departures([station])
        assert len(result) == 1
        assert result[0].line == "8"

    def test_filters_by_destination(self, monkeypatch):
        entries = [
            _make_entry("8", "Zürich, Kirche Fluntern", 5),
            _make_entry("8", "Zürich, Hardturm", 3),
        ]
        monkeypatch.setattr(
            "wetterstation.transit._fetch_stationboard",
            lambda sid: _make_api_response(entries),
        )

        station = _make_station()
        result = fetch_departures([station])
        assert len(result) == 1
        assert result[0].minutes >= 4  # the 5-minute one, not the 3-minute Hardturm

    def test_keeps_soonest_per_line(self, monkeypatch):
        entries = [
            _make_entry("8", "Zürich, Kirche Fluntern", 10),
            _make_entry("8", "Zürich, Kirche Fluntern", 3),
        ]
        monkeypatch.setattr(
            "wetterstation.transit._fetch_stationboard",
            lambda sid: _make_api_response(entries),
        )

        station = _make_station()
        result = fetch_departures([station])
        assert len(result) == 1
        assert result[0].minutes <= 3

    def test_multiple_lines(self, monkeypatch):
        entries = [
            _make_entry("8", "Zürich, Kirche Fluntern", 5),
            _make_entry("17", "Zürich, Bucheggplatz", 8),
        ]
        monkeypatch.setattr(
            "wetterstation.transit._fetch_stationboard",
            lambda sid: _make_api_response(entries),
        )

        station = _make_station(lines={
            "8": TransitLineConfig(
                color=(0, 128, 255),
                destinations=["Zürich, Kirche Fluntern"],
            ),
            "17": TransitLineConfig(
                color=(204, 0, 51),
                destinations=["Zürich, Bucheggplatz"],
            ),
        })
        result = fetch_departures([station])
        assert len(result) == 2
        lines = [d.line for d in result]
        assert "8" in lines
        assert "17" in lines

    def test_multiple_stations(self, monkeypatch):
        call_count = {"n": 0}

        def mock_fetch(sid):
            call_count["n"] += 1
            if sid == "111":
                return _make_api_response([
                    _make_entry("51", "Zürich, Seebach", 4),
                ])
            return _make_api_response([
                _make_entry("8", "Zürich, Kirche Fluntern", 6),
            ])

        monkeypatch.setattr("wetterstation.transit._fetch_stationboard", mock_fetch)

        stations = [
            _make_station(station_id="111", short="Sp", lines={
                "51": TransitLineConfig(color=(0, 180, 180), destinations=["Zürich, Seebach"]),
            }),
            _make_station(station_id="222", short="Be", lines={
                "8": TransitLineConfig(color=(0, 128, 255), destinations=["Zürich, Kirche Fluntern"]),
            }),
        ]
        result = fetch_departures(stations)
        assert len(result) == 2
        assert result[0].station_short == "Sp"
        assert result[1].station_short == "Be"

    def test_empty_stationboard(self, monkeypatch):
        monkeypatch.setattr(
            "wetterstation.transit._fetch_stationboard",
            lambda sid: _make_api_response([]),
        )

        station = _make_station()
        result = fetch_departures([station])
        assert result == []

    def test_api_error_skips_station(self, monkeypatch):
        def mock_fetch(sid):
            raise ConnectionError("timeout")

        monkeypatch.setattr("wetterstation.transit._fetch_stationboard", mock_fetch)

        station = _make_station()
        result = fetch_departures([station])
        assert result == []

    def test_departure_has_correct_color(self, monkeypatch):
        entries = [_make_entry("8", "Zürich, Kirche Fluntern", 5)]
        monkeypatch.setattr(
            "wetterstation.transit._fetch_stationboard",
            lambda sid: _make_api_response(entries),
        )

        station = _make_station()
        result = fetch_departures([station])
        assert result[0].color == (0, 128, 255)
