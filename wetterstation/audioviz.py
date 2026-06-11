"""Audio spectrum visualizer for AirPlay streaming.

Pipeline: ALSA loopback capture -> FFT -> 17 log-spaced bands -> LED bars.

Threading model (consistent with the rest of the project):
  - AudioAnalyzer runs capture + FFT in a daemon thread and only updates
    a bands array under a lock. It NEVER touches the display.
  - The main thread reads analyzer.bands and renders via spectrum_burst().
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Protocol, Sequence

import numpy as np

from wetterstation.config import AirplayConfig
from wetterstation.renderer import Color, DISPLAY_H, DISPLAY_W

log = logging.getLogger("wetterstation")

SAMPLE_RATE = 44100
FFT_SIZE = 2048
CHUNK_FRAMES = 1024


# ── DSP (pure functions) ─────────────────────────────────────────────────────

def band_edges(n_bands: int, f_min: float, f_max: float) -> np.ndarray:
    """Log-spaced frequency band edges (length n_bands + 1)."""
    return f_min * (f_max / f_min) ** (np.arange(n_bands + 1) / n_bands)


def bin_spectrum(
    power: np.ndarray,
    sample_rate: int,
    fft_size: int,
    edges: np.ndarray,
) -> np.ndarray:
    """Sum FFT power bins into frequency bands.

    Args:
        power: Power spectrum from rfft (length fft_size // 2 + 1).
        sample_rate: Audio sample rate in Hz.
        fft_size: FFT window size.
        edges: Band edge frequencies (length n_bands + 1).

    Returns:
        Array of n_bands band powers.
    """
    freqs = np.fft.rfftfreq(fft_size, d=1.0 / sample_rate)
    bands = np.zeros(len(edges) - 1)
    for i in range(len(edges) - 1):
        mask = (freqs >= edges[i]) & (freqs < edges[i + 1])
        if not mask.any():
            # Band narrower than one bin: take the nearest bin
            idx = int(np.argmin(np.abs(freqs - (edges[i] + edges[i + 1]) / 2)))
            bands[i] = power[idx]
        else:
            bands[i] = power[mask].sum()
    return bands


def build_gradient(stops: Sequence[Color], height: int = DISPLAY_H) -> list[Color]:
    """Interpolate color stops into one color per display row.

    Index 0 = bottom row of a bar, index height-1 = top.
    """
    if len(stops) == 1:
        return [tuple(stops[0])] * height  # type: ignore[list-item]
    rows: list[Color] = []
    for r in range(height):
        t = r / (height - 1) * (len(stops) - 1)
        i = min(int(t), len(stops) - 2)
        f = t - i
        rows.append(tuple(
            round(stops[i][k] + (stops[i + 1][k] - stops[i][k]) * f)
            for k in range(3)
        ))  # type: ignore[arg-type]
    return rows


class SpectrumProcessor:
    """Stateful spectrum analysis: window, FFT, dB mapping, AGC, smoothing."""

    def __init__(
        self,
        cfg: AirplayConfig,
        sample_rate: int = SAMPLE_RATE,
        fft_size: int = FFT_SIZE,
        n_bands: int = DISPLAY_W,
    ) -> None:
        self._cfg = cfg
        self._sample_rate = sample_rate
        self._fft_size = fft_size
        self._edges = band_edges(n_bands, cfg.freq_min, cfg.freq_max)
        self._window = np.hanning(fft_size).astype(np.float32)
        self._ring = np.zeros(fft_size, dtype=np.float32)
        self._values = np.zeros(n_bands, dtype=np.float32)
        # AGC: slowly decaying peak tracker (dB). Floor prevents silence
        # from amplifying noise to full scale.
        self._agc_ref_db = -20.0
        self._agc_min_db = -35.0
        self._agc_decay_db = 0.12  # per processed chunk (~5 dB/s at 43 Hz)

    def process(self, mono: np.ndarray) -> np.ndarray:
        """Feed a mono float32 chunk, return n_bands values in 0..1."""
        n = len(mono)
        if n >= self._fft_size:
            self._ring[:] = mono[-self._fft_size:]
        else:
            self._ring[:-n] = self._ring[n:]
            self._ring[-n:] = mono

        spectrum = np.fft.rfft(self._ring * self._window)
        power = np.abs(spectrum) ** 2 / self._fft_size
        bands = bin_spectrum(power, self._sample_rate, self._fft_size,
                             self._edges)
        db = 10.0 * np.log10(bands + 1e-10)

        if self._cfg.agc:
            peak = float(db.max())
            self._agc_ref_db = max(
                peak,
                self._agc_ref_db - self._agc_decay_db,
                self._agc_min_db,
            )
            ref = self._agc_ref_db
        else:
            ref = 0.0  # fixed 0 dBFS reference

        norm = (db - (ref + self._cfg.floor_db)) / -self._cfg.floor_db
        norm = np.clip(norm, 0.0, 1.0)

        # Asymmetric smoothing: fast attack, slow release
        rising = norm > self._values
        self._values[rising] += (
            (norm[rising] - self._values[rising]) * self._cfg.attack
        )
        self._values[~rising] *= 1.0 - self._cfg.release

        return self._values.copy()


# ── Audio sources ────────────────────────────────────────────────────────────

class AudioSource(Protocol):
    """A source of mono float32 audio chunks."""

    def read(self) -> np.ndarray | None:
        """Return next mono chunk, or None on timeout/no data."""
        ...

    def close(self) -> None: ...


class AlsaSource:
    """Capture from an ALSA device (loopback mirror of the AirPlay output)."""

    def __init__(self, device: str = "plughw:Loopback,1,0") -> None:
        import alsaaudio

        # Non-blocking: read() returns no data (instead of blocking forever)
        # when nothing is streaming into the loopback. The analyzer sleeps
        # briefly on empty reads, so it never busy-spins and stop() is clean.
        self._pcm = alsaaudio.PCM(
            alsaaudio.PCM_CAPTURE,
            alsaaudio.PCM_NONBLOCK,
            device=device,
            channels=2,
            rate=SAMPLE_RATE,
            format=alsaaudio.PCM_FORMAT_S16_LE,
            periodsize=CHUNK_FRAMES,
        )

    def read(self) -> np.ndarray | None:
        length, data = self._pcm.read()
        if length <= 0 or not data:
            return None
        samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)
        samples /= 32768.0
        # Interleaved stereo -> mono
        return (samples[0::2] + samples[1::2]) * 0.5

    def close(self) -> None:
        self._pcm.close()


class SyntheticSource:
    """Sine/noise generator for tests and Mac development (--viz-demo)."""

    def __init__(
        self,
        freq: float = 440.0,
        sample_rate: int = SAMPLE_RATE,
        amplitude: float = 0.5,
        noise: float = 0.0,
        realtime: bool = False,
    ) -> None:
        self._freq = freq
        self._sample_rate = sample_rate
        self._amplitude = amplitude
        self._noise = noise
        self._realtime = realtime
        self._phase = 0

    def read(self) -> np.ndarray | None:
        t = (np.arange(CHUNK_FRAMES) + self._phase) / self._sample_rate
        self._phase += CHUNK_FRAMES
        chunk = (self._amplitude * np.sin(2 * np.pi * self._freq * t)).astype(
            np.float32
        )
        if self._noise > 0:
            chunk += (self._noise * np.random.randn(CHUNK_FRAMES)).astype(
                np.float32
            )
        if self._realtime:
            time.sleep(CHUNK_FRAMES / self._sample_rate)
        return chunk

    def close(self) -> None:
        pass


class SweepSource(SyntheticSource):
    """Slowly sweeping sine for a lively demo display."""

    def read(self) -> np.ndarray | None:
        # Sweep 80 Hz .. 8 kHz over ~12 s
        cycle = (time.monotonic() % 12.0) / 12.0
        self._freq = 80.0 * (8000.0 / 80.0) ** cycle
        return super().read()


# ── Analyzer thread ──────────────────────────────────────────────────────────

class AudioAnalyzer:
    """Daemon thread: source.read() -> SpectrumProcessor -> self.bands.

    Robust against missing/failing ALSA devices: logs once, retries every
    5s, exposes zero bands meanwhile.
    """

    RETRY_SECS = 5.0

    def __init__(
        self,
        cfg: AirplayConfig,
        source_factory: Callable[[], AudioSource] | None = None,
        n_bands: int = DISPLAY_W,
    ) -> None:
        self._cfg = cfg
        self._n_bands = n_bands
        self._source_factory = source_factory or (
            lambda: AlsaSource(cfg.capture_device)
        )
        self._bands = [0.0] * n_bands
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def bands(self) -> list[float]:
        with self._lock:
            return list(self._bands)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        with self._lock:
            self._bands = [0.0] * self._n_bands

    def _run(self) -> None:
        processor = SpectrumProcessor(self._cfg, n_bands=self._n_bands)
        source: AudioSource | None = None
        error_logged = False
        while not self._stop.is_set():
            if source is None:
                try:
                    source = self._source_factory()
                    error_logged = False
                    log.info("Audio-Capture geöffnet (%s)",
                             self._cfg.capture_device)
                except Exception as e:
                    if not error_logged:
                        log.error("Audio-Capture fehlgeschlagen: %s "
                                  "(Retry alle %ds)", e, int(self.RETRY_SECS))
                        error_logged = True
                    if self._stop.wait(self.RETRY_SECS):
                        break
                    continue
            try:
                chunk = source.read()
            except Exception as e:
                log.error("Audio-Read fehlgeschlagen: %s", e)
                try:
                    source.close()
                except Exception:
                    pass
                source = None
                continue
            if chunk is None or len(chunk) == 0:
                # No data (e.g. visualizer on but nothing streaming into the
                # loopback). Sleep briefly so we never busy-spin a CPU core.
                self._stop.wait(0.01)
                continue
            values = processor.process(chunk)
            with self._lock:
                self._bands = values.tolist()

        if source is not None:
            try:
                source.close()
            except Exception:
                pass


# ── Renderer (main thread only) ──────────────────────────────────────────────

def draw_spectrum(
    display,
    bands: Sequence[float],
    gradient_rows: list[Color],
    peaks: list[float] | None = None,
    peak_color: Color | None = None,
) -> None:
    """Draw one spectrum frame: one bar per band, bottom-up.

    Note: y=0 is the TOP row of the display, so a bar of height h lights
    pixels y = H-1 .. H-h, colored by gradient_rows[row_from_bottom].
    """
    display.clear()
    height = display.height
    for x in range(min(len(bands), display.width)):
        lit = round(bands[x] * height)
        for row in range(lit):
            r, g, b = gradient_rows[row]
            display.set_pixel(x, height - 1 - row, r, g, b)
        if peaks is not None and peak_color is not None:
            pk = min(int(peaks[x]), height - 1)
            if pk >= lit and pk > 0:
                display.set_pixel(x, height - 1 - pk, *peak_color)
    display.show()


def spectrum_burst(
    display,
    analyzer: AudioAnalyzer,
    gradient_rows: list[Color],
    fps: int,
    interrupt: threading.Event,
    max_duration: float = 0.2,
    peaks: list[float] | None = None,
    peak_color: Color | None = None,
    state: dict | None = None,
) -> None:
    """Render spectrum frames for at most max_duration seconds.

    Returns to the caller so the main loop can process events; the
    AUDIO_VIZ state persists until an event replaces it. Checks the
    interrupt every frame, like all other animations.

    Only pushes a frame to the display when the rendered picture actually
    changes (frame-diffing). When the audio is silent/paused every frame is
    identical, so the expensive SPI show() is skipped and CPU/heat stay low.

    Args:
        peaks: Mutable per-band peak positions (rows), updated in place
            across bursts. None disables peak dots.
        state: Mutable dict carrying the last drawn signature across calls
            (owned by the caller). None disables frame-diffing.
    """
    height = display.height
    frame_time = 1.0 / fps
    end = time.monotonic() + max_duration
    while time.monotonic() < end:
        if interrupt.is_set():
            return
        frame_start = time.monotonic()
        bands = analyzer.bands
        if peaks is not None:
            for x in range(min(len(bands), len(peaks))):
                h = bands[x] * height
                if h > peaks[x]:
                    peaks[x] = h
                else:
                    peaks[x] = max(0.0, peaks[x] - 0.5)

        # Signature of what would be drawn; skip the redraw if unchanged.
        n = min(len(bands), display.width)
        heights = tuple(round(bands[x] * height) for x in range(n))
        peak_sig = (
            tuple(min(int(peaks[x]), height - 1) for x in range(n))
            if peaks is not None else None
        )
        sig = (heights, peak_sig)
        if state is None or sig != state.get("sig"):
            draw_spectrum(display, bands, gradient_rows, peaks, peak_color)
            if state is not None:
                state["sig"] = sig

        remaining = frame_time - (time.monotonic() - frame_start)
        if remaining > 0:
            if interrupt.wait(remaining):
                return
