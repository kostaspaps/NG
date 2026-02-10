# MVP Milestone A — Summary of Changes

## Files Created

| File | Purpose |
|------|---------|
| `requirements.txt` | Python dependencies (faster-whisper, pyaudio, pyyaml, numpy) |
| `profiles/vc_pitch_42cap.yaml` | 42CAP pitch profile with investor-specific context (Julian von Fischer, Adverity differentiation, tough question responses) |
| `profiles/vc_pitch_lupe.yaml` | Generic Lupe Analytics VC pitch profile |
| `audio.py` | Mic audio capture with in-memory ring buffer (~30s, 16kHz mono PCM). Thread-safe deque, start/stop controls, get_audio_window() returns float32 numpy array |
| `whisper_ctx.py` | Whisper context extraction using faster-whisper with Silero VAD gating. Background thread processes sliding 12s window every 1.5s. Exposes get_context() |
| `coach.py` | Claude CLI coaching agent. Reads YAML profiles, compiles system prompts, spawns `claude -p` with `--output-format json`. Robust JSON parsing handles markdown fences and envelope formats |
| `popup.py` | Always-on-top frameless tkinter overlay. Dark theme, draggable, shows one-liner/recommended/alternatives/warnings. Thread-safe updates via root.after(). Click to copy |
| `ng.py` | Main orchestrator with CLI entry point. Loads profile, starts audio/whisper/coach/popup pipeline. Graceful shutdown on Cmd+Q or Ctrl+C |
| `CONTEXT.md` | Root architecture context |
| `profiles/PROFILES_CONTEXT.md` | Profiles sub-context |
| `summary_changes.md` | This file |

## How to Install

### System dependencies (macOS)
```bash
# PortAudio is required for PyAudio
brew install portaudio
```

### Python dependencies
```bash
pip install -r requirements.txt
```

Note: `faster-whisper` will download the Whisper model on first run (~150MB for "small").

### Prerequisites
- **Claude CLI** must be installed and authenticated (`claude` command available in PATH)
- Python 3.10+
- macOS (for tkinter overlay and Cmd hotkeys)

## How to Run

```bash
# Start with 42CAP pitch profile (recommended for testing)
python3 ng.py --profile vc_pitch_42cap --whisper-model small

# Start with generic Lupe pitch profile
python3 ng.py --profile vc_pitch_lupe

# Use a different Whisper model
python3 ng.py --profile vc_pitch_42cap --whisper-model medium
```

### Controls
- **Cmd+Q** in the popup or **Ctrl+C** in the terminal to stop
- **Click** any suggestion text to copy to clipboard
- **Drag** the title bar to move the popup

---

# Milestone B — Dual Audio Capture: Summary of Changes

## New file: system_audio.py
ScreenCaptureKit-based system audio capture module for macOS 13+. Captures app/system audio (e.g., Zoom output) into an in-memory ring buffer. Provides the same public API as `AudioCapture` in `audio.py` so it works as a drop-in source for `WhisperContext`.

Key features:
- `SystemAudioCapture` class with `start_capture()`, `stop_capture()`, `get_audio_window(seconds)`, `clear_buffer()`, `is_capturing`, context manager support
- SCStreamOutput delegate receives CMSampleBuffers, converts to 16 kHz mono float32
- Linear interpolation resampling from source rate (typically 48 kHz) to 16 kHz
- Graceful handling: permission denial, macOS < 13, missing PyObjC bindings
- Zero disk writes

## Modified files

### whisper_ctx.py
- Added `label: str = "YOU"` parameter to `WhisperContext.__init__()`
- Changed hardcoded `[YOU]` to `[{self._label}]` in context string formatting
- Default behavior unchanged (label defaults to "YOU")

### ng.py
- Added `from system_audio import SystemAudioCapture` (wrapped in try/except ImportError)
- Added `--no-system-audio` CLI flag (action="store_true")
- `NGSession.__init__()` accepts `no_system_audio: bool = False`
- `start()`: creates SystemAudioCapture + second WhisperContext(label="THEM") after mic setup; wrapped in try/except for graceful fallback
- `_coaching_loop()`: merges context from both whisper instances with `"\n".join(filter(None, [mic_ctx, sys_ctx]))`
- `shutdown()`: stops system_whisper -> system_audio -> mic_whisper -> mic_audio in correct order

### coach.py
- Added dual-stream guidance text in `compile_prompt()` before existing response format instructions
- Reinforces [YOU]/[THEM] label semantics for the coaching agent

### Pipfile
- Added `pyobjc-framework-ScreenCaptureKit = "*"`
- Added `pyobjc-framework-AVFoundation = "*"`

## Unchanged files
- `audio.py` — no changes
- `popup.py` — no changes
- `profiles/*.yaml` — no changes

## New dependencies
- `pyobjc-framework-ScreenCaptureKit` — PyObjC bindings for ScreenCaptureKit
- `pyobjc-framework-AVFoundation` — PyObjC bindings for AVFoundation

## New CLI flag
- `--no-system-audio` — disables system audio capture, runs mic-only (identical to Milestone A behavior)

## Requirements
- **macOS 13.0+** for system audio capture via ScreenCaptureKit
- **Screen Recording permission** — macOS will prompt on first use; grant to Terminal/IDE
- Mic permission still required for mic capture

## Testing

### Mic-only mode (identical to Milestone A)
```bash
python3 ng.py --profile vc_pitch_42cap --whisper-model small --no-system-audio
```

### Dual audio capture
```bash
python3 ng.py --profile vc_pitch_42cap --whisper-model small
```
- Terminal output should show `[NG] System audio capture started (ScreenCaptureKit)`
- Context lines should show both `[YOU]: "..."` and `[THEM]: "..."` labels
- If system audio fails (permission, macOS version), falls back to mic-only automatically

## Known Limitations (after Milestone B)
- **No Ollama fallback** — only Claude CLI engine supported. `--engine ollama` exits with a message
- **No profile quick-switch** — must restart to change profiles
- **No Cmd+Space hide/show** — basic hotkeys only (Cmd+Q to quit)
- **No Cmd+1/2/3** — click alternative buttons to copy instead
- **Sequential Claude calls** — each context update spawns a new `claude -p` process (no persistent session)
- **English only** — Whisper language is hardcoded to "en"
