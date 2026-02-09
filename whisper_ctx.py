"""
whisper_ctx.py — Whisper context extraction module.

Captures a sliding window of audio from a provided audio capture object,
runs faster-whisper with Silero VAD gating, and exposes the latest
transcription as a labeled context string.

Usage:
    from audio_capture import AudioCapture  # or equivalent
    from whisper_ctx import WhisperContext

    ac = AudioCapture()
    ac.start()

    wc = WhisperContext(audio_capture=ac, model_size="small")
    wc.start()

    # Later...
    print(wc.get_context())  # '[YOU]: "hello world"'

    wc.stop()
"""

import logging
import threading
import time

import numpy as np
from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)

# Minimum RMS energy to consider a window as containing speech.
# Below this threshold we skip Whisper entirely to save compute.
_DEFAULT_ENERGY_THRESHOLD = 0.003


class WhisperContext:
    """Continuously transcribes a sliding audio window in a background thread.

    Parameters
    ----------
    audio_capture :
        An object exposing ``get_audio_window(seconds) -> np.ndarray``
        that returns mono float32 PCM in [-1, 1].
    model_size : str
        faster-whisper model identifier (``"small"``, ``"medium"``,
        ``"large-v3-turbo"``, etc.).  Downloaded to cache on first use.
    window_seconds : float
        Length of the audio window (seconds) fed to Whisper each cycle.
    interval : float
        Seconds to sleep between processing cycles.
    energy_threshold : float
        RMS energy below which the window is treated as silence and
        Whisper is not invoked.
    language : str
        Language code passed to ``model.transcribe()``.
    """

    def __init__(
        self,
        audio_capture,
        model_size: str = "small",
        window_seconds: float = 12.0,
        interval: float = 1.5,
        energy_threshold: float = _DEFAULT_ENERGY_THRESHOLD,
        language: str = "en",
    ):
        self._audio_capture = audio_capture
        self._model_size = model_size
        self._window_seconds = window_seconds
        self._interval = interval
        self._energy_threshold = energy_threshold
        self._language = language

        # Latest transcribed context string — overwritten each cycle.
        self._context: str = ""
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None

        # Load the model eagerly so callers know immediately if it fails.
        logger.info(
            "Loading faster-whisper model '%s' (first run downloads to cache)...",
            self._model_size,
        )
        self._model = WhisperModel(
            self._model_size,
            device="auto",
            compute_type="auto",
        )
        logger.info("Model '%s' loaded successfully.", self._model_size)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background transcription thread (daemon)."""
        if self._running:
            logger.warning("WhisperContext is already running.")
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._process_loop,
            name="whisper-ctx",
            daemon=True,
        )
        self._thread.start()
        logger.info("WhisperContext background thread started.")

    def stop(self) -> None:
        """Signal the background thread to stop and wait for it."""
        if not self._running:
            return

        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=self._interval * 3)
            self._thread = None
        logger.info("WhisperContext background thread stopped.")

    def get_context(self) -> str:
        """Return the latest context string.

        Returns a string such as ``'[YOU]: "hello world"'``, or an empty
        string if nothing has been transcribed yet.
        """
        with self._lock:
            return self._context

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _process_loop(self) -> None:
        """Background loop: grab audio, check energy, transcribe, store."""
        logger.debug("Entering processing loop (interval=%.2fs).", self._interval)

        while self._running:
            try:
                self._process_once()
            except Exception:
                logger.exception("Error during whisper processing cycle.")

            # Sleep in small increments so we can exit promptly on stop().
            deadline = time.monotonic() + self._interval
            while self._running and time.monotonic() < deadline:
                time.sleep(0.1)

    def _process_once(self) -> None:
        """Single processing cycle."""
        # 1. Obtain the audio window from the capture source.
        audio = self._audio_capture.get_audio_window(self._window_seconds)

        if audio is None or len(audio) == 0:
            return

        # Ensure float32 for both energy check and Whisper.
        audio = np.asarray(audio, dtype=np.float32)

        # 2. Quick energy gate — skip silence.
        rms = float(np.sqrt(np.mean(audio ** 2)))
        if rms < self._energy_threshold:
            logger.debug("Below energy threshold (rms=%.6f). Skipping.", rms)
            return

        # 3. Run faster-whisper with Silero VAD filter.
        segments, _info = self._model.transcribe(
            audio,
            vad_filter=True,
            language=self._language,
        )

        # segments is a lazy generator — materialise it.
        text = " ".join(seg.text.strip() for seg in segments)
        text = text.strip()

        if not text:
            logger.debug("Whisper returned empty transcription.")
            return

        # 4. Format as labeled context string (mic = YOU for MVP).
        context = f'[YOU]: "{text}"'

        # 5. Atomically overwrite the stored context.
        with self._lock:
            self._context = context

        logger.debug("Context updated: %s", context)
