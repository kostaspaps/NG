"""
system_audio.py -- System audio capture via ScreenCaptureKit (macOS 13+).

Captures system/app audio (e.g., Zoom output) using ScreenCaptureKit and
stores it in an in-memory ring buffer (~30 seconds). Provides the same
public API as AudioCapture so it can be used as a drop-in audio source
for WhisperContext.

Requires macOS 13.0+ and Screen Recording permission.
No disk writes of any kind.
"""

from __future__ import annotations

import collections
import logging
import platform
import threading
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# macOS version check
# ---------------------------------------------------------------------------
_macos_version: tuple[int, ...] = (0, 0, 0)
_SCK_AVAILABLE = False

_os_name = platform.system()
if _os_name == "Darwin":
    try:
        _ver_str = platform.mac_ver()[0]  # e.g. "13.5.2"
        _macos_version = tuple(int(x) for x in _ver_str.split("."))
    except (ValueError, AttributeError):
        _macos_version = (0, 0, 0)

# ---------------------------------------------------------------------------
# Conditional ScreenCaptureKit imports
# ---------------------------------------------------------------------------
try:
    if _os_name != "Darwin" or _macos_version < (13,):
        raise ImportError("macOS 13+ required for ScreenCaptureKit")

    import ScreenCaptureKit as SCK  # pyobjc-framework-ScreenCaptureKit
    import CoreMedia  # pyobjc-framework-Quartz includes CoreMedia
    from Foundation import NSObject
    import dispatch  # pyobjc-core includes libdispatch bindings

    _SCK_AVAILABLE = True
except ImportError as _import_err:
    _SCK_IMPORT_ERROR = str(_import_err)
    _SCK_AVAILABLE = False

# ---------------------------------------------------------------------------
# Constants (match audio.py for Whisper compatibility)
# ---------------------------------------------------------------------------
TARGET_RATE: int = 16000        # Whisper expects 16 kHz
MAX_SECONDS: int = 30           # ring buffer capacity
_AUDIO_OUTPUT_TYPE: int = 1     # SCStreamOutputType.audio


class SystemAudioCaptureError(Exception):
    """Raised when system audio capture fails."""


class SystemAudioCapture:
    """Captures system audio via ScreenCaptureKit into an in-memory ring buffer.

    Public API mirrors AudioCapture for drop-in compatibility with WhisperContext.

    Usage::

        cap = SystemAudioCapture()
        cap.start_capture()
        audio = cap.get_audio_window(5)   # last 5 seconds as float32 numpy array
        cap.stop_capture()
    """

    def __init__(self) -> None:
        if not _SCK_AVAILABLE:
            raise SystemAudioCaptureError(
                f"ScreenCaptureKit not available: {_SCK_IMPORT_ERROR}"
            )

        # Ring buffer stores float32 numpy chunks at TARGET_RATE (16 kHz).
        # At 16 kHz, 30 seconds = 480,000 samples. We store as list of arrays.
        self._lock = threading.Lock()
        self._buffer: collections.deque[np.ndarray] = collections.deque(
            maxlen=TARGET_RATE * MAX_SECONDS  # worst case: 1-sample chunks
        )
        self._total_samples: int = 0

        # Capture state
        self._capturing = False
        self._permission_denied = False
        self._stream = None  # SCStream
        self._delegate = None  # stream output delegate

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------
    @property
    def is_capturing(self) -> bool:
        """Return *True* while the capture is actively running."""
        return self._capturing

    # ------------------------------------------------------------------
    # Start / stop controls
    # ------------------------------------------------------------------
    def start_capture(self) -> None:
        """Request Screen Recording permission and start system audio capture.

        Raises
        ------
        SystemAudioCaptureError
            If ScreenCaptureKit is unavailable or permission is denied.
        """
        if self._capturing:
            return  # idempotent

        if not _SCK_AVAILABLE:
            raise SystemAudioCaptureError("ScreenCaptureKit not available")

        # Request shareable content (triggers permission dialog on first use).
        # This is async via completion handler — we use a threading.Event to
        # synchronize.
        content_ready = threading.Event()
        shareable_content = [None]
        content_error = [None]

        def _on_content(content, error):
            if error:
                content_error[0] = error
            else:
                shareable_content[0] = content
            content_ready.set()

        SCK.SCShareableContent.getShareableContentWithCompletionHandler_(
            _on_content
        )

        # Wait up to 30 seconds for user to grant permission
        if not content_ready.wait(timeout=30.0):
            self._permission_denied = True
            raise SystemAudioCaptureError(
                "Timed out waiting for Screen Recording permission"
            )

        if content_error[0] is not None:
            self._permission_denied = True
            raise SystemAudioCaptureError(
                f"Screen Recording permission denied or error: {content_error[0]}"
            )

        content = shareable_content[0]
        if content is None:
            self._permission_denied = True
            raise SystemAudioCaptureError(
                "No shareable content returned"
            )

        try:
            self._start_stream(content)
        except Exception as exc:
            logger.warning("Failed to start SCStream: %s", exc)
            raise SystemAudioCaptureError(
                f"Failed to start system audio stream: {exc}"
            ) from exc

    def _start_stream(self, content) -> None:
        """Configure and start the SCStream for audio-only capture."""
        # Configure: audio only, no video
        config = SCK.SCStreamConfiguration.alloc().init()
        config.setCapturesAudio_(True)
        config.setExcludesCurrentProcessAudio_(True)
        config.setSampleRate_(TARGET_RATE)  # Request 16 kHz directly if supported
        config.setChannelCount_(1)  # mono

        # Create a content filter that captures all desktop audio.
        # We use a display-based filter with no excluded apps.
        displays = content.displays()
        if not displays or len(displays) == 0:
            raise SystemAudioCaptureError("No displays found for audio capture")

        # Use the main display to create a filter; we only want audio,
        # and video frames will be discarded.
        main_display = displays[0]
        content_filter = SCK.SCContentFilter.alloc().initWithDisplay_excludingApplications_exceptingWindows_(
            main_display, [], []
        )

        # Create delegate to receive audio samples
        self._delegate = _SCStreamOutputHandler.alloc().init()
        self._delegate._parent = self

        # Create and configure the stream
        stream = SCK.SCStream.alloc().initWithFilter_configuration_delegate_(
            content_filter, config, None
        )

        # Create a dedicated serial dispatch queue for audio callbacks
        audio_queue = dispatch.dispatch_queue_create(
            b"com.lupe.ng.systemaudio", None
        )

        # Add stream output for audio; check for registration error
        success, reg_error = stream.addStreamOutput_type_sampleHandlerQueue_error_(
            self._delegate,
            _AUDIO_OUTPUT_TYPE,
            audio_queue,
            None,
        )
        if not success or reg_error is not None:
            raise SystemAudioCaptureError(
                f"Failed to register stream output: {reg_error}"
            )

        # Start the stream (async with completion handler)
        start_ready = threading.Event()
        start_error = [None]

        def _on_start(err):
            if err:
                start_error[0] = err
            start_ready.set()

        stream.startCaptureWithCompletionHandler_(_on_start)

        if not start_ready.wait(timeout=10.0):
            raise SystemAudioCaptureError("Timed out starting SCStream")

        if start_error[0] is not None:
            raise SystemAudioCaptureError(
                f"SCStream start failed: {start_error[0]}"
            )

        self._stream = stream
        self._capturing = True
        logger.info("System audio capture started via ScreenCaptureKit")

    def stop_capture(self) -> None:
        """Stop system audio capture and release resources.

        Safe to call even if capture is not running (no-op).
        """
        if not self._capturing and self._stream is None:
            return

        self._capturing = False

        if self._stream is not None:
            stop_ready = threading.Event()

            def _on_stop(err):
                if err:
                    logger.warning("Error stopping SCStream: %s", err)
                stop_ready.set()

            try:
                self._stream.stopCaptureWithCompletionHandler_(_on_stop)
                stop_ready.wait(timeout=5.0)
            except Exception as exc:
                logger.warning("Exception stopping SCStream: %s", exc)

            self._stream = None

        self._delegate = None
        logger.info("System audio capture stopped")

    # ------------------------------------------------------------------
    # Data retrieval
    # ------------------------------------------------------------------
    def get_audio_window(self, seconds: float) -> np.ndarray:
        """Return the most recent *seconds* of captured system audio.

        Parameters
        ----------
        seconds : float
            Number of seconds to retrieve. Clamped to MAX_SECONDS.

        Returns
        -------
        numpy.ndarray
            1-D float32 array with samples in the range [-1.0, 1.0].
            Returns an empty array when the buffer is empty or permission
            was denied.
        """
        if self._permission_denied:
            return np.array([], dtype=np.float32)

        seconds = min(seconds, MAX_SECONDS)
        if seconds <= 0:
            return np.array([], dtype=np.float32)

        samples_needed = int(TARGET_RATE * seconds)

        with self._lock:
            if not self._buffer:
                return np.array([], dtype=np.float32)

            # Concatenate all chunks
            all_audio = np.concatenate(list(self._buffer))

        if len(all_audio) == 0:
            return np.array([], dtype=np.float32)

        # Return only the last N samples
        if len(all_audio) > samples_needed:
            all_audio = all_audio[-samples_needed:]

        return all_audio

    def clear_buffer(self) -> None:
        """Discard all buffered audio."""
        with self._lock:
            self._buffer.clear()
            self._total_samples = 0

    # ------------------------------------------------------------------
    # Audio data handler (called by delegate)
    # ------------------------------------------------------------------
    def _handle_audio_buffer(self, sample_buffer) -> None:
        """Process an incoming CMSampleBuffer from ScreenCaptureKit.

        Extracts audio data, converts to 16 kHz mono float32, and appends
        to the ring buffer.
        """
        try:
            # Get the audio buffer list from the CMSampleBuffer
            block_buffer = CoreMedia.CMSampleBufferGetDataBuffer(sample_buffer)
            if block_buffer is None:
                return

            # Get raw data from the block buffer
            length = CoreMedia.CMBlockBufferGetDataLength(block_buffer)
            if length == 0:
                return

            # PyObjC returns (OSStatus, buffer) tuple from CMBlockBufferCopyDataBytes
            result = CoreMedia.CMBlockBufferCopyDataBytes(
                block_buffer, 0, length, None
            )
            if isinstance(result, tuple):
                status, raw_data = result
            else:
                # Fallback if PyObjC returns just a status
                status = result
                raw_data = None

            if status != 0:
                logger.warning("CMBlockBufferCopyDataBytes failed with status %d", status)
                return
            if raw_data is None:
                return

            data_bytes = bytes(raw_data)

            # Get the format description to determine sample rate and format
            fmt_desc = CoreMedia.CMSampleBufferGetFormatDescription(sample_buffer)
            if fmt_desc is None:
                # Assume configured format: 16 kHz, mono, float32
                audio = np.frombuffer(data_bytes, dtype=np.float32)
            else:
                # Get the basic audio description
                # PyObjC may return the ASBD as a struct or as a tuple:
                # (mSampleRate, mFormatID, mFormatFlags, mBytesPerPacket,
                #  mFramesPerPacket, mBytesPerFrame, mChannelsPerFrame,
                #  mBitsPerChannel, mReserved)
                asbd = CoreMedia.CMAudioFormatDescriptionGetStreamBasicDescription(
                    fmt_desc
                )
                if asbd is not None:
                    if isinstance(asbd, tuple):
                        source_rate = int(asbd[0])
                        format_flags = int(asbd[2])
                        channels = int(asbd[6])
                        bits = int(asbd[7])
                    else:
                        source_rate = int(asbd.mSampleRate)
                        channels = int(asbd.mChannelsPerFrame)
                        bits = int(asbd.mBitsPerChannel)
                        format_flags = int(asbd.mFormatFlags)

                    # CoreAudio format flag constants
                    kAudioFormatFlagIsFloat = 1 << 0           # 0x1
                    kAudioFormatFlagIsSignedInteger = 1 << 2   # 0x4
                    kAudioFormatFlagIsNonInterleaved = 1 << 5  # 0x20

                    is_float = bool(format_flags & kAudioFormatFlagIsFloat)
                    is_non_interleaved = bool(format_flags & kAudioFormatFlagIsNonInterleaved)

                    # Parse based on format flags and bit depth
                    if is_float and bits == 32:
                        audio = np.frombuffer(data_bytes, dtype=np.float32)
                    elif is_float and bits == 64:
                        audio = np.frombuffer(data_bytes, dtype=np.float64).astype(np.float32)
                    elif bits == 16:
                        audio = np.frombuffer(data_bytes, dtype=np.int16).astype(
                            np.float32
                        ) / 32768.0
                    elif bits == 32:
                        # 32-bit signed integer PCM
                        audio = np.frombuffer(data_bytes, dtype=np.int32).astype(
                            np.float32
                        ) / 2147483648.0
                    else:
                        # Fallback: try float32
                        logger.warning(
                            "Unknown audio format: bits=%d flags=0x%x, trying float32",
                            bits, format_flags,
                        )
                        audio = np.frombuffer(data_bytes, dtype=np.float32)

                    # Convert to mono if stereo (interleaved)
                    if channels > 1 and not is_non_interleaved:
                        audio = audio.reshape(-1, channels).mean(axis=1)
                    elif channels > 1 and is_non_interleaved:
                        # Non-interleaved: take first channel only
                        frames = len(audio) // channels
                        audio = audio[:frames]

                    # Resample if not at target rate
                    if source_rate != TARGET_RATE and source_rate > 0:
                        audio = self._resample(audio, source_rate, TARGET_RATE)
                else:
                    audio = np.frombuffer(data_bytes, dtype=np.float32)

            # Clip to [-1, 1] range
            audio = np.clip(audio, -1.0, 1.0).astype(np.float32)

            if len(audio) == 0:
                return

            # Append to ring buffer, trimming to max capacity
            max_samples = TARGET_RATE * MAX_SECONDS
            with self._lock:
                self._buffer.append(audio)
                self._total_samples += len(audio)

                # Trim old chunks if over capacity
                while self._total_samples > max_samples and self._buffer:
                    removed = self._buffer.popleft()
                    self._total_samples -= len(removed)

        except Exception as exc:
            logger.warning("Error processing audio buffer: %s", exc)

    @staticmethod
    def _resample(audio: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
        """Simple linear interpolation resampling."""
        if source_rate == target_rate or len(audio) == 0:
            return audio

        ratio = target_rate / source_rate
        new_length = int(len(audio) * ratio)
        if new_length == 0:
            return np.array([], dtype=np.float32)

        indices = np.linspace(0, len(audio) - 1, new_length)
        return np.interp(indices, np.arange(len(audio)), audio).astype(np.float32)

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------
    def __enter__(self) -> "SystemAudioCapture":
        self.start_capture()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop_capture()

    def __del__(self) -> None:
        try:
            self.stop_capture()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# SCStreamOutput delegate — receives audio CMSampleBuffers
# ---------------------------------------------------------------------------
if _SCK_AVAILABLE:
    class _SCStreamOutputHandler(NSObject):
        """Objective-C delegate that receives audio sample buffers from SCStream."""

        _parent: Optional[SystemAudioCapture] = None

        def stream_didOutputSampleBuffer_ofType_(
            self, stream, sample_buffer, output_type
        ):
            """Called by ScreenCaptureKit when a new audio buffer is available.

            output_type 1 = audio.
            """
            if output_type != _AUDIO_OUTPUT_TYPE:  # Only process audio
                return
            if self._parent is not None:
                self._parent._handle_audio_buffer(sample_buffer)
