"""Tests for wetterstation.audioviz: DSP, gradient, renderer, analyzer."""

import threading
import time

import numpy as np
import pytest

from wetterstation.audioviz import (
    AudioAnalyzer,
    SpectrumProcessor,
    SyntheticSource,
    band_edges,
    bin_spectrum,
    build_gradient,
    draw_spectrum,
    spectrum_burst,
    FFT_SIZE,
    SAMPLE_RATE,
)
from wetterstation.config import AirplayConfig
from wetterstation.simulator import SimulatorBackend


@pytest.fixture
def cfg() -> AirplayConfig:
    return AirplayConfig()


def make_sine(freq: float, n: int = FFT_SIZE) -> np.ndarray:
    t = np.arange(n) / SAMPLE_RATE
    return (0.5 * np.sin(2 * np.pi * freq * t)).astype(np.float32)


class TestBandEdges:
    def test_length(self):
        edges = band_edges(17, 40, 16000)
        assert len(edges) == 18

    def test_endpoints(self):
        edges = band_edges(17, 40, 16000)
        assert edges[0] == pytest.approx(40)
        assert edges[-1] == pytest.approx(16000)

    def test_log_spaced(self):
        edges = band_edges(17, 40, 16000)
        ratios = edges[1:] / edges[:-1]
        assert np.allclose(ratios, ratios[0])

    def test_monotonic(self):
        edges = band_edges(17, 40, 16000)
        assert (np.diff(edges) > 0).all()


class TestBinSpectrum:
    def test_sine_lands_in_correct_band(self):
        edges = band_edges(17, 40, 16000)
        for freq in (440.0, 8000.0):
            sine = make_sine(freq)
            power = np.abs(np.fft.rfft(sine * np.hanning(FFT_SIZE))) ** 2
            bands = bin_spectrum(power, SAMPLE_RATE, FFT_SIZE, edges)
            expected = int(np.searchsorted(edges, freq) - 1)
            assert int(np.argmax(bands)) == expected

    def test_band_count(self):
        edges = band_edges(17, 40, 16000)
        power = np.zeros(FFT_SIZE // 2 + 1)
        assert len(bin_spectrum(power, SAMPLE_RATE, FFT_SIZE, edges)) == 17


class TestSpectrumProcessor:
    def test_silence_gives_zero(self, cfg):
        proc = SpectrumProcessor(cfg)
        values = proc.process(np.zeros(FFT_SIZE, dtype=np.float32))
        assert (values == 0).all()

    def test_sine_peaks_in_correct_band(self, cfg):
        proc = SpectrumProcessor(cfg)
        edges = band_edges(17, cfg.freq_min, cfg.freq_max)
        for _ in range(5):
            values = proc.process(make_sine(440.0))
        expected = int(np.searchsorted(edges, 440.0) - 1)
        assert int(np.argmax(values)) == expected
        assert values[expected] > 0.5

    def test_noise_lights_all_bands(self, cfg):
        proc = SpectrumProcessor(cfg)
        rng = np.random.default_rng(42)
        for _ in range(5):
            values = proc.process(
                rng.standard_normal(FFT_SIZE).astype(np.float32) * 0.3
            )
        assert (values > 0).all()

    def test_release_decays_slowly(self, cfg):
        proc = SpectrumProcessor(cfg)
        for _ in range(5):
            values = proc.process(make_sine(440.0))
        peak_band = int(np.argmax(values))
        peak_value = values[peak_band]
        after_one = proc.process(np.zeros(FFT_SIZE, dtype=np.float32))
        # One silent chunk must not erase the bar (slow release)
        assert after_one[peak_band] > peak_value * 0.5
        for _ in range(60):
            values = proc.process(np.zeros(FFT_SIZE, dtype=np.float32))
        assert values[peak_band] < 0.05

    def test_agc_normalizes_quiet_signal(self, cfg):
        proc = SpectrumProcessor(cfg)
        quiet = make_sine(440.0) * 0.05  # ~-30 dB vs full scale
        for _ in range(10):
            values = proc.process(quiet)
        assert values.max() > 0.8


class TestBuildGradient:
    def test_row_count(self):
        rows = build_gradient([(0, 0, 0), (255, 255, 255)], height=7)
        assert len(rows) == 7

    def test_endpoints_match_stops(self):
        stops = [(60, 60, 200), (180, 140, 220), (220, 40, 80)]
        rows = build_gradient(stops, height=7)
        assert rows[0] == (60, 60, 200)
        assert rows[-1] == (220, 40, 80)

    def test_midpoint_interpolated(self):
        rows = build_gradient([(0, 0, 0), (100, 200, 60)], height=3)
        assert rows[1] == (50, 100, 30)

    def test_single_stop(self):
        rows = build_gradient([(10, 20, 30)], height=7)
        assert rows == [(10, 20, 30)] * 7


class TestDrawSpectrum:
    def test_bar_heights(self):
        display = SimulatorBackend()
        gradient = build_gradient([(60, 60, 200), (220, 40, 80)])
        bands = [0.0] * 17
        bands[0] = 0.0
        bands[1] = 0.5
        bands[2] = 1.0
        draw_spectrum(display, bands, gradient)

        col0 = [display.get_pixel(0, y) for y in range(7)]
        assert all(p == (0, 0, 0) for p in col0)

        col1_lit = sum(
            1 for y in range(7) if display.get_pixel(1, y) != (0, 0, 0)
        )
        assert col1_lit == round(0.5 * 7)

        col2_lit = sum(
            1 for y in range(7) if display.get_pixel(2, y) != (0, 0, 0)
        )
        assert col2_lit == 7

    def test_gradient_colors_bottom_up(self):
        display = SimulatorBackend()
        gradient = build_gradient([(60, 60, 200), (220, 40, 80)])
        bands = [1.0] + [0.0] * 16
        draw_spectrum(display, bands, gradient)
        assert display.get_pixel(0, 6) == gradient[0]   # bottom row
        assert display.get_pixel(0, 0) == gradient[6]   # top row

    def test_peak_dot_drawn(self):
        display = SimulatorBackend()
        gradient = build_gradient([(60, 60, 200), (220, 40, 80)])
        bands = [0.3] + [0.0] * 16
        peaks = [6.0] + [0.0] * 16
        peak_color = (160, 160, 230)
        draw_spectrum(display, bands, gradient, peaks, peak_color)
        assert display.get_pixel(0, 0) == peak_color


class TestSpectrumBurst:
    def _analyzer(self) -> AudioAnalyzer:
        cfg = AirplayConfig()
        analyzer = AudioAnalyzer(
            cfg, source_factory=lambda: SyntheticSource(freq=440.0)
        )
        return analyzer

    def test_respects_max_duration(self):
        display = SimulatorBackend()
        analyzer = self._analyzer()
        gradient = build_gradient([(60, 60, 200), (220, 40, 80)])
        interrupt = threading.Event()
        start = time.monotonic()
        spectrum_burst(display, analyzer, gradient, fps=25,
                       interrupt=interrupt, max_duration=0.2)
        assert time.monotonic() - start < 0.5

    def test_returns_immediately_on_interrupt(self):
        display = SimulatorBackend()
        analyzer = self._analyzer()
        gradient = build_gradient([(60, 60, 200), (220, 40, 80)])
        interrupt = threading.Event()
        interrupt.set()
        start = time.monotonic()
        spectrum_burst(display, analyzer, gradient, fps=25,
                       interrupt=interrupt, max_duration=5.0)
        assert time.monotonic() - start < 0.1

    def test_renders_frames(self):
        display = SimulatorBackend()
        analyzer = self._analyzer()
        gradient = build_gradient([(60, 60, 200), (220, 40, 80)])
        interrupt = threading.Event()
        spectrum_burst(display, analyzer, gradient, fps=25,
                       interrupt=interrupt, max_duration=0.15)
        assert display.show_count >= 2


class _FixedAnalyzer:
    """Analyzer stub returning constant bands (for frame-diff tests)."""

    def __init__(self, bands):
        self._bands = bands

    @property
    def bands(self):
        return list(self._bands)


class TestFrameDiffing:
    def test_state_skips_unchanged_frames(self):
        display = SimulatorBackend()
        gradient = build_gradient([(60, 60, 200), (220, 40, 80)])
        analyzer = _FixedAnalyzer([0.5] * 17)
        state = {}
        spectrum_burst(display, analyzer, gradient, fps=100,
                       interrupt=threading.Event(), max_duration=0.15,
                       state=state)
        # Constant bands → draw once, skip the rest.
        assert display.show_count == 1

    def test_without_state_draws_every_frame(self):
        display = SimulatorBackend()
        gradient = build_gradient([(60, 60, 200), (220, 40, 80)])
        analyzer = _FixedAnalyzer([0.5] * 17)
        spectrum_burst(display, analyzer, gradient, fps=100,
                       interrupt=threading.Event(), max_duration=0.15)
        assert display.show_count >= 3

    def test_state_redraws_on_change(self):
        display = SimulatorBackend()
        gradient = build_gradient([(60, 60, 200), (220, 40, 80)])
        analyzer = _FixedAnalyzer([0.5] * 17)
        state = {}
        spectrum_burst(display, analyzer, gradient, fps=100,
                       interrupt=threading.Event(), max_duration=0.05,
                       state=state)
        first = display.show_count
        analyzer._bands = [1.0] * 17  # picture changes
        spectrum_burst(display, analyzer, gradient, fps=100,
                       interrupt=threading.Event(), max_duration=0.05,
                       state=state)
        assert display.show_count > first


class TestAudioAnalyzer:
    def test_produces_bands(self):
        cfg = AirplayConfig()
        analyzer = AudioAnalyzer(
            cfg, source_factory=lambda: SyntheticSource(freq=440.0)
        )
        analyzer.start()
        try:
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                if max(analyzer.bands) > 0.5:
                    break
                time.sleep(0.02)
            assert max(analyzer.bands) > 0.5
        finally:
            analyzer.stop()

    def test_stop_resets_bands(self):
        cfg = AirplayConfig()
        analyzer = AudioAnalyzer(
            cfg, source_factory=lambda: SyntheticSource(freq=440.0)
        )
        analyzer.start()
        time.sleep(0.1)
        analyzer.stop()
        assert analyzer.bands == [0.0] * 17

    def test_failing_source_yields_zero_bands(self):
        cfg = AirplayConfig()

        def broken_factory():
            raise OSError("no such device")

        analyzer = AudioAnalyzer(cfg, source_factory=broken_factory)
        analyzer.start()
        time.sleep(0.1)
        try:
            assert analyzer.bands == [0.0] * 17
        finally:
            analyzer.stop()
