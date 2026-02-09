"""
coach.py -- Claude CLI coaching agent module.

Reads a YAML negotiation profile, compiles it into a system prompt,
and spawns the `claude` CLI in print mode to get per-turn coaching
suggestions as structured JSON.
"""

import json
import re
import subprocess
from pathlib import Path

import yaml


# ---------------------------------------------------------------------------
# Profile I/O
# ---------------------------------------------------------------------------

def read_profile(path: str) -> dict:
    """Read a YAML profile file and return it as a dict."""
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# ---------------------------------------------------------------------------
# Prompt compilation
# ---------------------------------------------------------------------------

def _bullet_list(items: list[str]) -> str:
    """Format a list of strings as a markdown-style bullet list."""
    return "\n".join(f"  - {item}" for item in items)


def _compile_special_context(special: dict) -> str:
    """Render the special_context block into readable paragraphs."""
    lines: list[str] = []

    if "adverity_differentiation" in special:
        lines.append(
            f"Adverity differentiation context:\n{special['adverity_differentiation'].strip()}"
        )

    if "investor_background" in special:
        lines.append(
            f"Investor background:\n{special['investor_background'].strip()}"
        )

    if "fund_details" in special:
        lines.append(
            f"Fund details:\n{special['fund_details'].strip()}"
        )

    if "questions_for_julian" in special:
        qs = _bullet_list(special["questions_for_julian"])
        lines.append(f"Good questions to ask the investor:\n{qs}")

    if "tough_question_responses" in special:
        tqr = special["tough_question_responses"]
        parts = [f"  - {k}: {v}" for k, v in tqr.items()]
        lines.append(f"Prepared tough-question responses:\n" + "\n".join(parts))

    # Catch-all for any other keys we haven't explicitly handled.
    handled = {
        "adverity_differentiation",
        "investor_background",
        "fund_details",
        "questions_for_julian",
        "tough_question_responses",
    }
    for key in sorted(set(special.keys()) - handled):
        value = special[key]
        if isinstance(value, str):
            lines.append(f"{key}:\n{value.strip()}")
        elif isinstance(value, list):
            lines.append(f"{key}:\n{_bullet_list(value)}")
        else:
            lines.append(f"{key}: {value}")

    return "\n\n".join(lines)


def compile_prompt(profile: dict) -> str:
    """Compile a profile dict into a full system prompt string."""

    goals = profile.get("goals", {})
    constraints = profile.get("constraints", {})
    tone = profile.get("tone", {})
    key_points = profile.get("key_points", [])
    preferred_moves = profile.get("preferred_moves", [])

    parts: list[str] = [
        f"You are my personal negotiation coach. My goal: {goals.get('primary', 'Win the negotiation')}.",
        f"Key points I must hit:\n{_bullet_list(key_points)}",
        f"I must not reveal:\n{_bullet_list(constraints.get('do_not_reveal', []))}",
        f"I must not commit to:\n{_bullet_list(constraints.get('do_not_commit', []))}",
        f"My preferred tone: {tone.get('default', 'calm and confident')}.",
        f"My preferred tactics:\n{_bullet_list(preferred_moves)}",
    ]

    # Optional special context section.
    special = profile.get("special_context")
    if special:
        parts.append(_compile_special_context(special))

    # Response format instructions.
    parts.append(
        'I will send you conversation context labeled [THEM] (the other party) and [YOU] (me).\n'
        'Focus your suggestions on how I should respond to what THEY are saying.\n'
        'Respond ONLY with a JSON object:\n'
        '{\n'
        '  "one_liner": "What to say next, <= 140 chars",\n'
        '  "recommended": "1-2 sentence response",\n'
        '  "alternatives": [\n'
        '    {"label": "Collaborative", "text": "..."},\n'
        '    {"label": "Assertive", "text": "..."},\n'
        '    {"label": "Probing", "text": "..."}\n'
        '  ],\n'
        '  "next_question": "A calibrated question to ask",\n'
        '  "avoid": ["Don\'t say X", "Don\'t concede Y"],\n'
        '  "risk": "Brief risk warning or null"\n'
        '}\n\n'
        'Be concise. Every suggestion must be short and glanceable.'
    )

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

_FALLBACK: dict = {
    "one_liner": "Listening...",
    "recommended": "Listening...",
    "alternatives": [
        {"label": "Collaborative", "text": "Listening..."},
        {"label": "Assertive", "text": "Listening..."},
        {"label": "Probing", "text": "Listening..."},
    ],
    "next_question": "Listening...",
    "avoid": [],
    "risk": None,
}


def parse_response(raw: str) -> dict:
    """Parse a JSON coaching response from the Claude CLI.

    Handles:
    - Plain JSON
    - Markdown-fenced JSON (```json ... ```)
    - Nested ``result`` key emitted by --output-format json

    Returns a fallback dict with 'Listening...' placeholders when
    parsing fails.
    """
    if not raw or not raw.strip():
        return dict(_FALLBACK)

    text = raw.strip()

    # 1. The --output-format json envelope: {"result": "..."}
    try:
        envelope = json.loads(text)
        if isinstance(envelope, dict) and "result" in envelope:
            text = envelope["result"]
            # The inner value may itself be a JSON string or a dict.
            if isinstance(text, dict):
                return _normalise(text)
            text = str(text).strip()
    except (json.JSONDecodeError, TypeError):
        pass

    # 2. Strip markdown code fences if present.
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()

    # 3. Try to parse the (possibly unwrapped) JSON.
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return _normalise(data)
    except (json.JSONDecodeError, TypeError):
        pass

    # 4. Last resort: look for the first { ... } block.
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        try:
            data = json.loads(brace_match.group(0))
            if isinstance(data, dict):
                return _normalise(data)
        except (json.JSONDecodeError, TypeError):
            pass

    return dict(_FALLBACK)


def _normalise(data: dict) -> dict:
    """Ensure the parsed dict has every expected key with correct types."""
    return {
        "one_liner": str(data.get("one_liner", "Listening...")),
        "recommended": str(data.get("recommended", "Listening...")),
        "alternatives": data.get("alternatives", _FALLBACK["alternatives"]),
        "next_question": str(data.get("next_question", "Listening...")),
        "avoid": data.get("avoid", []),
        "risk": data.get("risk"),
    }


# ---------------------------------------------------------------------------
# Coaching agent
# ---------------------------------------------------------------------------

class CoachAgent:
    """Wraps the ``claude`` CLI to provide per-turn negotiation coaching.

    Each call to :meth:`send_context` spawns a fresh ``claude -p`` process
    so there is no persistent session state on the CLI side.
    """

    def __init__(self, system_prompt: str):
        self._system_prompt = system_prompt
        self._process: subprocess.CompletedProcess | None = None

    # ---- public API -------------------------------------------------------

    def send_context(self, context_str: str) -> dict:
        """Send conversation context and return coaching suggestions.

        Parameters
        ----------
        context_str:
            Free-form text, typically containing ``[THEM]`` and ``[YOU]``
            labelled dialogue turns.

        Returns
        -------
        dict
            Parsed coaching suggestion with keys ``one_liner``,
            ``recommended``, ``alternatives``, ``next_question``,
            ``avoid``, ``risk``.
        """
        user_message = f"{context_str}\nGive me your coaching suggestions."

        cmd = [
            "claude",
            "--system-prompt", self._system_prompt,
            "-p", user_message,
            "--output-format", "json",
        ]

        try:
            self._process = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if self._process.returncode != 0:
                # Log stderr for debugging but return a usable fallback.
                _stderr = self._process.stderr.strip()
                if _stderr:
                    print(f"[coach] claude CLI error: {_stderr}")
                return dict(_FALLBACK)

            return parse_response(self._process.stdout)

        except subprocess.TimeoutExpired:
            print("[coach] claude CLI timed out after 30 s")
            return dict(_FALLBACK)
        except FileNotFoundError:
            print("[coach] 'claude' CLI not found on PATH")
            return dict(_FALLBACK)
        except Exception as exc:  # noqa: BLE001
            print(f"[coach] unexpected error: {exc}")
            return dict(_FALLBACK)

    def kill(self):
        """Kill any running subprocess (no-op in print mode, provided
        for interface compatibility)."""
        # In print mode subprocess.run() blocks until completion, so
        # there is nothing to kill.  This method exists for forward
        # compatibility if we later switch to a persistent session.
        self._process = None
