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

## Current state (Milestone A)
- Mic-only capture (no system audio yet)
- Claude CLI engine only (no Ollama fallback yet)
- Basic tkinter popup overlay
- Two profiles: vc_pitch_42cap (42CAP-specific), vc_pitch_lupe (generic)
