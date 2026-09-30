"""Audio helpers: PCM conversion, WAV I/O, resampling, and signal synthesis.

All audio inside voicebench is mono float32 in the range [-1.0, 1.0]. Adapters
convert to and from 16-bit little-endian PCM at the transport boundary.
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float32]

_INT16_SCALE = 32768.0


def ms_to_samples(ms: float, sample_rate: int) -> int:
    """Convert a duration in milliseconds to a whole number of samples."""
    return round(ms * sample_rate / 1000.0)


def samples_to_ms(samples: int, sample_rate: int) -> float:
    """Convert a sample count to milliseconds."""
    return samples * 1000.0 / sample_rate


def to_pcm16(audio: FloatArray) -> bytes:
    """Encode float audio as 16-bit little-endian PCM bytes, clipping out-of-range values."""
    clipped = np.clip(audio, -1.0, 1.0 - 1.0 / _INT16_SCALE)
    return (clipped * _INT16_SCALE).astype("<i2").tobytes()


def from_pcm16(data: bytes) -> FloatArray:
    """Decode 16-bit little-endian PCM bytes into float audio."""
    if len(data) % 2:
        raise ValueError("PCM16 payload must have an even number of bytes")
    ints = np.frombuffer(data, dtype="<i2")
    return (ints.astype(np.float32) / _INT16_SCALE).astype(np.float32)


def resample(audio: FloatArray, src_rate: int, dst_rate: int) -> FloatArray:
    """Resample with linear interpolation.

    Linear interpolation is enough for timing analysis, which only needs the
    energy envelope. It is not meant for listening-quality conversion.
    """
    if src_rate == dst_rate or audio.size == 0:
        return audio.astype(np.float32, copy=False)
    duration = audio.size / src_rate
    n_out = max(1, round(duration * dst_rate))
    src_t = np.arange(audio.size, dtype=np.float64) / src_rate
    dst_t = np.arange(n_out, dtype=np.float64) / dst_rate
    return np.interp(dst_t, src_t, audio).astype(np.float32)


def read_wav(path: str | Path, sample_rate: int) -> FloatArray:
    """Read a PCM WAV file, downmix to mono, and resample to ``sample_rate``."""
    with wave.open(str(path), "rb") as wf:
        channels = wf.getnchannels()
        width = wf.getsampwidth()
        rate = wf.getframerate()
        raw = wf.readframes(wf.getnframes())
    if width == 2:
        data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / _INT16_SCALE
    elif width == 1:
        data = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif width == 4:
        data = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"{path}: unsupported sample width {width * 8} bits")
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    return resample(data.astype(np.float32), rate, sample_rate)


def write_wav(path: str | Path, audio: FloatArray, sample_rate: int) -> None:
    """Write mono float audio as a 16-bit PCM WAV file."""
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(to_pcm16(audio))


def db_to_amplitude(db: float) -> float:
    """Convert dBFS to a linear amplitude (0 dBFS is full scale)."""
    return float(10.0 ** (db / 20.0))


def rms_dbfs(audio: FloatArray) -> float:
    """Return the RMS level of ``audio`` in dBFS, floored at -120."""
    if audio.size == 0:
        return -120.0
    rms = float(np.sqrt(np.mean(np.square(audio, dtype=np.float64))))
    if rms <= 1e-6:
        return -120.0
    return max(-120.0, 20.0 * float(np.log10(rms)))


def silence(duration_ms: float, sample_rate: int) -> FloatArray:
    """Return digital silence."""
    return np.zeros(ms_to_samples(duration_ms, sample_rate), dtype=np.float32)


def tone(
    duration_ms: float,
    sample_rate: int,
    freq_hz: float = 440.0,
    level_db: float = -20.0,
) -> FloatArray:
    """Return a sine tone whose RMS level is ``level_db`` dBFS, with 5 ms fades."""
    n = ms_to_samples(duration_ms, sample_rate)
    t = np.arange(n, dtype=np.float64) / sample_rate
    peak = db_to_amplitude(level_db) * np.sqrt(2.0)
    out = (peak * np.sin(2.0 * np.pi * freq_hz * t)).astype(np.float32)
    return _fade(out, sample_rate)


def noise(
    duration_ms: float,
    sample_rate: int,
    level_db: float = -30.0,
    seed: int = 0,
) -> FloatArray:
    """Return white noise whose RMS level is ``level_db`` dBFS."""
    n = ms_to_samples(duration_ms, sample_rate)
    rng = np.random.default_rng(seed)
    out = rng.standard_normal(n) * db_to_amplitude(level_db)
    return _fade(out.astype(np.float32), sample_rate)


def speech_like(
    duration_ms: float,
    sample_rate: int,
    level_db: float = -20.0,
    f0_hz: float = 140.0,
    syllable_rate_hz: float = 4.0,
    seed: int = 0,
) -> FloatArray:
    """Return a speech-shaped test signal.

    The signal is a harmonic complex on a wandering fundamental, amplitude
    modulated at a syllable rate. Energy-based detectors treat it like voiced
    speech. Speech-to-text engines and neural VADs do not, so use recorded
    speech when you benchmark a production agent.
    """
    n = ms_to_samples(duration_ms, sample_rate)
    if n == 0:
        return np.zeros(0, dtype=np.float32)
    rng = np.random.default_rng(seed)
    t = np.arange(n, dtype=np.float64) / sample_rate
    wander = 1.0 + 0.08 * np.sin(2.0 * np.pi * 0.7 * t + rng.uniform(0, 2 * np.pi))
    phase = 2.0 * np.pi * np.cumsum(f0_hz * wander) / sample_rate
    nyquist = sample_rate / 2.0
    voiced = np.zeros(n, dtype=np.float64)
    for k in range(1, 12):
        if k * f0_hz * 1.1 >= nyquist:
            break
        voiced += np.sin(k * phase) / k
    # Syllable envelope stays above 0.35 so short dips do not read as pauses.
    env = 0.35 + 0.65 * (0.5 + 0.5 * np.sin(2.0 * np.pi * syllable_rate_hz * t - np.pi / 2))
    out = voiced * env
    rms = float(np.sqrt(np.mean(out**2)))
    if rms > 0:
        out *= db_to_amplitude(level_db) / rms
    return _fade(out.astype(np.float32), sample_rate)


def _fade(audio: FloatArray, sample_rate: int, fade_ms: float = 5.0) -> FloatArray:
    n = min(ms_to_samples(fade_ms, sample_rate), audio.size // 2)
    if n > 0:
        ramp = np.linspace(0.0, 1.0, n, dtype=np.float32)
        audio[:n] *= ramp
        audio[-n:] *= ramp[::-1]
    return audio
