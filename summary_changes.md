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

## Known Limitations (MVP)

- **Mic only** — no system audio capture (no ScreenCaptureKit integration yet). Only your voice is transcribed (`[YOU]`), not the other party
- **No Ollama fallback** — only Claude CLI engine supported. `--engine ollama` exits with a message
- **No profile quick-switch** — must restart to change profiles
- **No Cmd+Space hide/show** — basic hotkeys only (Cmd+Q to quit)
- **No Cmd+1/2/3** — click alternative buttons to copy instead
- **Sequential Claude calls** — each context update spawns a new `claude -p` process (no persistent session)
- **English only** — Whisper language is hardcoded to "en"
