"""
audio.py -- Mic audio capture module with in-memory ring buffer.

Captures 16 kHz / mono / 16-bit PCM audio from the default microphone
and stores raw byte chunks in a thread-safe ring buffer (~30 seconds).
Designed to feed Whisper-compatible audio without touching the disk.
"""

from __future__ import annotations

import collections
import struct
import threading
from typing import Optional

import numpy as np
import pyaudio

# ---------------------------------------------------------------------------
# Module-level constants (Whisper-compatible defaults)
# ---------------------------------------------------------------------------
RATE: int = 16000                   # 16 kHz sample rate
CHANNELS: int = 1                   # mono
FORMAT: int = pyaudio.paInt16       # 16-bit signed PCM
CHUNK: int = 1024                   # frames per buffer callback
MAX_SECONDS: int = 30               # ring buffer capacity in seconds

# Derived: how many chunks fit in MAX_SECONDS
_CHUNKS_PER_SECOND: float = RATE / CHUNK
_MAX_CHUNKS: int = int(_CHUNKS_PER_SECOND * MAX_SECONDS) + 1


class AudioCaptureError(Exception):
    """Raised when the microphone cannot be opened or a capture error occurs."""


class AudioCapture:
    """Continuously captures microphone audio into a fixed-size ring buffer.

    Usage::

        cap = AudioCapture()
        cap.start_capture()
        # ... later ...
        audio = cap.get_audio_window(5)   # last 5 seconds as float32 numpy array
        cap.stop_capture()
    """

    def __init__(
        self,
        rate: int = RATE,
        channels: int = CHANNELS,
        fmt: int = FORMAT,
        chunk: int = CHUNK,
        max_seconds: int = MAX_SECONDS,
    ) -> None:
        self._rate = rate
        self._channels = channels
        self._format = fmt
        self._chunk = chunk
        self._max_seconds = max_seconds

        # Derived buffer capacity (number of chunks)
        chunks_per_second = self._rate / self._chunk
        self._max_chunks = int(chunks_per_second * self._max_seconds) + 1

        # Thread-safe ring buffer: stores raw PCM byte strings
        self._lock = threading.Lock()
        self._buffer: collections.deque[bytes] = collections.deque(
            maxlen=self._max_chunks
        )

        # Capture state
        self._capturing = False
        self._thread: Optional[threading.Thread] = None
        self._pa: Optional[pyaudio.PyAudio] = None
        self._stream: Optional[pyaudio.Stream] = None

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------
    @property
    def is_capturing(self) -> bool:
        """Return *True* while the capture loop is actively recording."""
        return self._capturing

    # ------------------------------------------------------------------
    # Start / stop controls
    # ------------------------------------------------------------------
    def start_capture(self) -> None:
        """Open the default microphone and begin filling the ring buffer.

        Raises
        ------
        AudioCaptureError
            If no input device is available or the stream cannot be opened.
        """
        if self._capturing:
            return  # already running -- idempotent

        # Initialise PyAudio and validate that a mic exists
        self._pa = pyaudio.PyAudio()

        default_input = self._pa.get_default_input_device_info()
        if default_input is None:
            self._pa.terminate()
            self._pa = None
            raise AudioCaptureError("No default input device found.")

        try:
            self._stream = self._pa.open(
                format=self._format,
                channels=self._channels,
                rate=self._rate,
                input=True,
                frames_per_buffer=self._chunk,
            )
        except (OSError, IOError) as exc:
            self._pa.terminate()
            self._pa = None
            raise AudioCaptureError(
                f"Could not open microphone stream: {exc}"
            ) from exc

        self._capturing = True

        self._thread = threading.Thread(
            target=self._capture_loop, daemon=True, name="audio-capture"
        )
        self._thread.start()

    def stop_capture(self) -> None:
        """Stop recording and release audio resources.

        Safe to call even if capture is not running (no-op).
        """
        if not self._capturing:
            return

        self._capturing = False

        # Wait for the capture thread to finish
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

        # Close the stream
        if self._stream is not None:
            try:
                if self._stream.is_active():
                    self._stream.stop_stream()
                self._stream.close()
            except (OSError, IOError):
                pass  # best-effort cleanup
            self._stream = None

        # Terminate PyAudio
        if self._pa is not None:
            self._pa.terminate()
            self._pa = None

    # ------------------------------------------------------------------
    # Data retrieval
    # ------------------------------------------------------------------
    def get_audio_window(self, seconds: float) -> np.ndarray:
        """Return the most recent *seconds* of captured audio.

        Parameters
        ----------
        seconds : float
            Number of seconds to retrieve.  Clamped to ``MAX_SECONDS``
            and to however much audio is actually available (which may
            be less if capture just started).

        Returns
        -------
        numpy.ndarray
            1-D float32 array with samples in the range [-1.0, 1.0].
            Returns an empty array (shape ``(0,)``) when the buffer is
            empty.
        """
        seconds = min(seconds, self._max_seconds)
        if seconds <= 0:
            return np.array([], dtype=np.float32)

        chunks_needed = int((self._rate / self._chunk) * seconds) + 1

        with self._lock:
            # Grab the tail of the deque (most recent chunks)
            available = list(self._buffer)

        if not available:
            return np.array([], dtype=np.float32)

        tail = available[-chunks_needed:]

        raw_bytes = b"".join(tail)

        # Convert int16 PCM to float32 [-1, 1]
        sample_count = len(raw_bytes) // 2  # 2 bytes per int16 sample
        if sample_count == 0:
            return np.array([], dtype=np.float32)

        samples = np.frombuffer(raw_bytes[:sample_count * 2], dtype=np.int16)
        audio_f32 = samples.astype(np.float32) / 32768.0

        # Trim to exactly the requested number of samples
        max_samples = int(self._rate * seconds)
        if len(audio_f32) > max_samples:
            audio_f32 = audio_f32[-max_samples:]

        return audio_f32

    def clear_buffer(self) -> None:
        """Discard all buffered audio."""
        with self._lock:
            self._buffer.clear()

    # ------------------------------------------------------------------
    # Internal capture loop
    # ------------------------------------------------------------------
    def _capture_loop(self) -> None:
        """Read chunks from the mic stream until ``stop_capture`` is called."""
        while self._capturing:
            try:
                data = self._stream.read(self._chunk, exception_on_overflow=False)
            except (OSError, IOError):
                # Stream error (device unplugged, etc.) -- stop gracefully.
                self._capturing = False
                break

            with self._lock:
                self._buffer.append(data)

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------
    def __enter__(self) -> "AudioCapture":
        self.start_capture()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop_capture()

    def __del__(self) -> None:
        # Best-effort cleanup if the caller forgets to stop
        try:
            self.stop_capture()
        except Exception:
            pass
