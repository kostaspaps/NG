# System Audio Context

Detailed design decisions and change log for `system_audio.py` — ScreenCaptureKit-based system audio capture.

## What changed (Milestone B review fixes)

### Must-fix: mutable buffer for CMBlockBufferCopyDataBytes
- **Before:** `bytes(length)` (immutable) was passed as the output buffer — `CMBlockBufferCopyDataBytes` could silently fail or raise, leaving `[THEM]` transcription empty.
- **After:** Uses `ctypes.c_char * length` mutable buffer. The `OSStatus` return is checked; non-zero status logs a warning and skips the buffer.
- **Import change:** `struct` removed, `ctypes` added.

### Must-fix: dedicated dispatch queue for stream output
- **Before:** `addStreamOutput_type_sampleHandlerQueue_error_` was called with `sampleHandlerQueue=None` (default queue) and its return value was ignored. If registration failed, capture appeared started but no callbacks arrived.
- **After:** A dedicated serial dispatch queue (`com.lupe.ng.systemaudio`) is created via `dispatch.dispatch_queue_create()`. The `(success, error)` return tuple is checked; failure raises `SystemAudioCaptureError`.
- **Import change:** `objc` removed, `dispatch` added (from pyobjc-core libdispatch bindings).

### Should-fix: fail-fast error model in start_capture()
- **Before:** Permission denial/timeouts returned silently (`logger.warning` + `return`), leaving the caller unaware that capture never started.
- **After:** All failure paths raise `SystemAudioCaptureError`. The caller (`ng.py`) catches these in a try/except and falls back to mic-only mode.

### Should-fix: ASBD format flag parsing
- **Before:** Audio format decoding relied only on `mBitsPerChannel`, which couldn't distinguish 32-bit float vs 32-bit integer PCM.
- **After:** `mFormatFlags` is parsed for `kAudioFormatFlagIsFloat` (0x1), `kAudioFormatFlagIsSignedInteger` (0x4), and `kAudioFormatFlagIsNonInterleaved` (0x20). Supported formats:
  - float32 (most common from ScreenCaptureKit)
  - float64 (downcast to float32)
  - int16 PCM (÷ 32768)
  - int32 PCM (÷ 2147483648)
  - Non-interleaved multi-channel: first channel extracted
  - Interleaved multi-channel: averaged to mono
  - Unknown: fallback to float32 with warning log

### Should-fix: error log level promotion
- `_handle_audio_buffer` exceptions promoted from `logger.debug` to `logger.warning` for production visibility.

## Key design decisions

- **Drop-in API:** `SystemAudioCapture` mirrors `AudioCapture`'s public interface (`start_capture()`, `stop_capture()`, `get_audio_window(seconds)`, `is_capturing`) so `WhisperContext` can consume either source without changes.
- **Ring buffer:** `collections.deque` of numpy float32 chunks, capped at 30s × 16kHz = 480k samples. Thread-safe via `threading.Lock`.
- **Linear interpolation resampling:** Simple `np.interp`-based resampling from source rate to 16kHz target. Adequate quality for speech; avoids scipy dependency.
- **Zero disk writes:** All audio data stays in memory. No temp files, no logs of audio content.

## Dependencies
- `pyobjc-framework-ScreenCaptureKit` — ScreenCaptureKit Python bindings
- `pyobjc-framework-Quartz` — includes CoreMedia
- `pyobjc-core` — includes Foundation, libdispatch bindings
- `numpy` — audio buffer operations
- macOS 13.0+ required; Screen Recording permission required

## Orchestrator integration (ng.py)
- `ng.py` creates `SystemAudioCapture` in a try/except; any `SystemAudioCaptureError` triggers mic-only fallback.
- The `[THEM]` WhisperContext is only created when `self._system_audio.is_capturing` is True (not just when the object exists).

## Testing notes
- **Permission-denied test:** Mock `SCShareableContent.getShareableContentWithCompletionHandler_` to return an error; assert `SystemAudioCaptureError` is raised and `is_capturing` remains False.
- **Audio-buffer decode test:** Feed a mocked `CMSampleBuffer` with known PCM samples; assert `get_audio_window()` returns non-empty float32 data with expected values.
- **Stream-output registration failure:** Make `addStreamOutput_type_sampleHandlerQueue_error_` return `(False, error)`; assert `SystemAudioCaptureError` is raised.
- **Graceful fallback in ng.py:** Assert that when `start_capture()` raises, `NGSession` continues with `_system_whisper is None`.
