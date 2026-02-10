# NG — Architecture Context

**What:** Local negotiation co-pilot. Captures mic audio, extracts context with local Whisper, feeds it to Claude CLI, shows coaching suggestions in an always-on-top popup.

**Architecture:** Single Python process with 4 modules + popup.

```
audio.py  →  whisper_ctx.py  →  coach.py  →  popup.py
(mic)        (STT)              (Claude)     (overlay)
                    ↑
              ng.py (orchestrator)
```

**Key principles:**
- Zero persistence: no audio, text, or logs saved to disk
- In-memory only: ring buffer, ephemeral context strings
- Profile-driven: YAML profiles compiled into system prompts
- Claude CLI as brain: `claude -p --system-prompt "..." --output-format json`

## Sub-context files
- `profiles/PROFILES_CONTEXT.md` — profile schema and available profiles

## Current state (Milestone B)
- Dual audio capture: mic (PyAudio) + system audio (ScreenCaptureKit, macOS 13+)
- Two WhisperContext instances: mic → `[YOU]`, system audio → `[THEM]`
- Merged context fed to coach: `[YOU]: "..." \n [THEM]: "..."`
- `--no-system-audio` flag for mic-only fallback (identical to Milestone A)
- Graceful degradation if ScreenCaptureKit unavailable (permission denied, macOS < 13, missing pyobjc)
- Claude CLI engine only (no Ollama fallback yet)
- Basic tkinter popup overlay
- Two profiles: vc_pitch_42cap (42CAP-specific), vc_pitch_lupe (generic)

### New module: system_audio.py
- ScreenCaptureKit-based system audio capture
- Same public API as audio.py's AudioCapture (drop-in for WhisperContext)
- Ring buffer with linear-interpolation resampling to 16 kHz mono float32
- Zero disk writes
