#!/usr/bin/env python3
"""NG — Local Negotiation Co-Pilot.

Main orchestrator: load profile → compile prompt → start audio capture →
start whisper processing → spawn Claude agent → open popup.

Zero persistence guaranteed. Everything is in-memory and destroyed on exit.
"""

import argparse
import signal
import sys
import threading
import time

from audio import AudioCapture
from whisper_ctx import WhisperContext
from coach import CoachAgent, read_profile, compile_prompt
from popup import CoachPopup


class NGSession:
    """Manages the full lifecycle of a negotiation coaching session."""

    def __init__(self, profile_path: str, whisper_model: str = "small"):
        self._profile_path = profile_path
        self._whisper_model = whisper_model

        self._audio: AudioCapture | None = None
        self._whisper: WhisperContext | None = None
        self._coach: CoachAgent | None = None
        self._popup: CoachPopup | None = None

        self._running = False
        self._last_context = ""
        self._coach_thread: threading.Thread | None = None

    def start(self):
        """Start all components and open the popup."""
        # 1. Load profile and compile system prompt
        profile = read_profile(self._profile_path)
        system_prompt = compile_prompt(profile)
        profile_name = profile.get("name", "Unknown")

        print(f"[NG] Profile loaded: {profile_name}")
        print(f"[NG] Whisper model: {self._whisper_model}")

        # 2. Start audio capture
        self._audio = AudioCapture()
        self._audio.start_capture()
        print("[NG] Audio capture started")

        # 3. Start Whisper context extraction
        self._whisper = WhisperContext(
            self._audio,
            model_size=self._whisper_model,
            window_seconds=12,
            interval=1.5,
        )
        self._whisper.start()
        print("[NG] Whisper context extraction started")

        # 4. Create coach agent
        self._coach = CoachAgent(system_prompt)
        print("[NG] Coach agent ready")

        # 5. Start the coaching loop in a background thread
        self._running = True
        self._coach_thread = threading.Thread(
            target=self._coaching_loop, daemon=True
        )
        self._coach_thread.start()

        # 6. Create and run popup (blocks on mainloop)
        self._popup = CoachPopup(profile_name=profile_name)
        self._popup.set_on_quit(self.shutdown)
        self._popup.set_status(True)
        print("[NG] Popup opened — session active")
        print("[NG] Press Cmd+Q in the popup or Ctrl+C here to stop.")

        # This blocks until the popup is closed
        self._popup.run()

    def _coaching_loop(self):
        """Background loop: context → coach → popup updates."""
        while self._running:
            try:
                context = self._whisper.get_context() if self._whisper else ""

                # Only send to coach if context has changed and is non-empty
                if context and context != self._last_context:
                    self._last_context = context
                    print(f"[NG] Context: {context[:80]}...")

                    suggestions = self._coach.send_context(context)

                    if self._popup and suggestions:
                        self._popup.update_suggestions(suggestions)
                        self._popup.set_status(True)

                time.sleep(1.0)

            except Exception as e:
                print(f"[NG] Coaching loop error: {e}")
                time.sleep(2.0)

    def shutdown(self):
        """Clean shutdown: kill everything, clear all state."""
        if not self._running:
            return

        print("\n[NG] Shutting down...")
        self._running = False

        # Stop whisper
        if self._whisper:
            self._whisper.stop()
            self._whisper = None
            print("[NG] Whisper stopped")

        # Stop audio capture
        if self._audio:
            self._audio.stop_capture()
            self._audio = None
            print("[NG] Audio capture stopped")

        # Kill coach agent
        if self._coach:
            self._coach.kill()
            self._coach = None
            print("[NG] Coach agent killed")

        # Clear state
        self._last_context = ""

        # Destroy popup
        if self._popup:
            try:
                self._popup.destroy()
            except Exception:
                pass
            self._popup = None
            print("[NG] Popup closed")

        print("[NG] Session destroyed — zero trace left.")


def main():
    parser = argparse.ArgumentParser(
        description="NG — Local Negotiation Co-Pilot"
    )
    parser.add_argument(
        "--profile",
        required=True,
        help="Profile name (resolves to profiles/<name>.yaml)",
    )
    parser.add_argument(
        "--whisper-model",
        default="small",
        choices=["tiny", "base", "small", "medium", "large-v3-turbo"],
        help="Whisper model size (default: small)",
    )
    parser.add_argument(
        "--engine",
        default="claude",
        choices=["claude", "ollama"],
        help="LLM engine (default: claude). Ollama not yet implemented.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model name for Ollama engine (e.g., llama3:8b)",
    )

    args = parser.parse_args()

    if args.engine == "ollama":
        print("[NG] Ollama engine not yet implemented. Use --engine claude.")
        sys.exit(1)

    # Resolve profile path
    profile_path = f"profiles/{args.profile}.yaml"

    # Create and start session
    session = NGSession(
        profile_path=profile_path,
        whisper_model=args.whisper_model,
    )

    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        session.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    try:
        session.start()
    except KeyboardInterrupt:
        session.shutdown()
    except Exception as e:
        print(f"[NG] Fatal error: {e}")
        session.shutdown()
        sys.exit(1)


if __name__ == "__main__":
    main()
