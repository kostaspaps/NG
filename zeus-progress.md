# Milestone B — Dual Audio Capture (Mic + System Audio via ScreenCaptureKit)
**Started:** 2026-02-10 10:30
**Branch:** feat/dual-audio-capture
**Template:** full

## Progress

- [x] Read and understand all source files (audio.py, whisper_ctx.py, ng.py, coach.py, Pipfile, CONTEXT.md, ng.md)
- [x] Update Pipfile — added pyobjc-framework-ScreenCaptureKit and pyobjc-framework-AVFoundation (Pipfile)
- [x] Create system_audio.py — ScreenCaptureKit system audio capture module with identical API to AudioCapture (system_audio.py)
- [x] Update whisper_ctx.py — added `label` parameter, replaced hardcoded `[YOU]` with `[{self._label}]` (whisper_ctx.py)
- [x] Update ng.py — dual audio sources, merged context in coaching loop, --no-system-audio flag, graceful fallback (ng.py)
- [x] Update coach.py — added dual-stream guidance text to compile_prompt() (coach.py)
- [x] Verify no regressions — audio.py, popup.py, profiles/ unchanged; all syntax checks pass; no disk writes in system_audio.py
- [x] No test suite found (no tests/ dir, no test_*.py files)
- [x] Update CONTEXT.md and write summary_changes.md — updated CONTEXT.md to Milestone B state, appended Milestone B section to summary_changes.md
