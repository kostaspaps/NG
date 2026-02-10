# NG — Architecture Context

**What:** Local negotiation co-pilot. Captures mic audio, extracts context with local Whisper, feeds it to Claude CLI, shows coaching suggestions in an always-on-top popup.

**Architecture:** Single Python process with 5 modules + popup.

```
audio.py          →  whisper_ctx.py  →  coach.py  →  popup.py
(mic)                (STT, [YOU])       (Claude)     (overlay)
system_audio.py   →  whisper_ctx.py
(system, [THEM])     (STT, [THEM])
                          ↑
                    ng.py (orchestrator)
```

**Key principles:**
- Zero persistence: no audio, text, or logs saved to disk
- In-memory only: ring buffer, ephemeral context strings
- Profile-driven: YAML profiles compiled into system prompts
- Claude CLI as brain: `claude -p --system-prompt "..." --output-format json`
- Fail-fast with graceful degradation: system audio errors raise exceptions, caller falls back to mic-only

## Sub-Context Files
- `profiles/PROFILES_CONTEXT.md` — profile schema and available profiles
- `SYSTEM_AUDIO_CONTEXT.md` — system audio capture design, format handling, and error model

## Current state (Milestone B — post-review)
- Dual audio capture: mic (PyAudio) + system audio (ScreenCaptureKit, macOS 13+)
- Two WhisperContext instances: mic → `[YOU]`, system audio → `[THEM]`
- Merged context fed to coach: `[YOU]: "..." \n [THEM]: "..."`
- `--no-system-audio` flag for mic-only fallback (identical to Milestone A)
- Graceful degradation if ScreenCaptureKit unavailable (permission denied, macOS < 13, missing pyobjc)
- ng.py gates `[THEM]` WhisperContext on `is_capturing` — prevents orphaned workers when system audio fails
- coach.py prompt: consolidated [YOU]/[THEM] labeling into a single instruction block
- Claude CLI engine only (no Ollama fallback yet)
- Basic tkinter popup overlay
- Two profiles: vc_pitch_42cap (42CAP-specific), vc_pitch_lupe (generic)

### Module: system_audio.py
See `SYSTEM_AUDIO_CONTEXT.md` for detailed design decisions and error model.
