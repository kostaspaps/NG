# Implement MVP Milestone A — Mic Capture + Whisper + Claude CLI + Popup
**Started:** 2026-02-09 22:51
**Branch:** feat/mvp-milestone-a
**Template:** full

## Progress

- [x] Read ng.md and 42cap prep.md specs — full understanding of requirements
- [x] Create requirements.txt — faster-whisper, pyaudio, pyyaml, numpy
- [x] Create profiles/vc_pitch_42cap.yaml — 42CAP pitch profile with investor context, Adverity differentiation, tough Q responses
- [x] Create profiles/vc_pitch_lupe.yaml — generic Lupe Analytics VC pitch profile
- [x] Create audio.py — mic capture with thread-safe ring buffer, 16kHz mono PCM, get_audio_window() returns float32 numpy
- [x] Create whisper_ctx.py — faster-whisper with Silero VAD gating, background thread, sliding 12s window every 1.5s
- [x] Create coach.py — read_profile, compile_prompt, CoachAgent (claude -p --output-format json), robust parse_response
- [x] Create popup.py — frameless tkinter overlay, dark theme, draggable, thread-safe updates, click-to-copy
- [x] Create ng.py — main orchestrator with CLI args, pipeline orchestration, graceful shutdown
- [x] Fix popup.py alternatives format — convert list-of-dicts from coach to dict for button lookup
- [x] Create CONTEXT.md and profiles/PROFILES_CONTEXT.md
- [x] Create summary_changes.md
- [x] Verify all Python files compile cleanly (py_compile)
- [x] Test integration — all Python files compile clean, coach smoke tests pass, zero persistence verified (no open() in write mode)
- [x] No test runner found (no pytest/npm/make config exists)
- [ ] Commit all changes
