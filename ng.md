ng.md — Local Negotiation Co-Pilot

A dead-simple local tool: captures audio, extracts context with local Whisper, feeds it to a Claude CLI agent loaded with your negotiation profile, and shows short suggestions in a small popup. No API keys to manage, no servers, no recording, no persistence.

0) Product Summary
What it is

A personal negotiation coach that runs as a simple local script:

1. You run `./ng start --profile vc_pitch`
2. A small always-on-top popup window opens
3. It listens to your audio (mic + system), extracts context with local Whisper (in memory, ephemeral)
4. A Claude CLI agent (pre-loaded with your profile/goals) receives the context and returns short suggestions
5. The popup shows one-liners and short response options you can glance at
6. When you stop, everything is destroyed. Zero trace.

That's it. No servers, no WebSockets, no React app, no API keys to configure.

How it works under the hood

Audio capture (PyAudio / ScreenCaptureKit) → in-memory buffer
        ↓
Local Whisper (whisper.cpp / faster-whisper) → ephemeral text context
        ↓  (audio buffer discarded immediately)
Claude CLI agent (spawned with profile as system prompt) → short suggestions JSON
        ↓
Simple popup overlay (always-on-top) → display suggestions
        ↓  (on session end: all memory wiped)

Why Claude CLI, no API keys

Claude CLI (`claude`) is already installed and authenticated locally. It handles its own auth — no OpenAI/Gemini API keys to manage. Before each session, a fresh Claude agent is spawned with your profile YAML compiled into a system prompt. The agent only lives for the duration of your call.

Optionally, for fully offline operation (zero network), swap Claude CLI for a local LLM via Ollama (e.g., Llama 3, Mistral). Lower quality but 100% air-gapped.

What it is NOT

Not a recording tool. Zero audio is ever saved or persisted.

Not a transcription tool. Whisper runs in memory to extract context; the text is fed to Claude and then discarded. No transcript UI.

Not a tool that involves the other party. Only you see the popup. This is your personal notepad.

Why this is fully legal

Nothing is recorded, stored, or transmitted. Audio passes through memory for context extraction and is immediately discarded. Functionally identical to reading your own notes during a call.

1) Core User Stories

US1 — VC Pitch: While on a call, glance at the popup for a one-liner, 2-3 short alternatives, and a "next question" to regain control.

US2 — Negotiation: See short response options labeled by tactic (mirror, label, anchor) and quick warnings ("don't concede pricing yet").

US3 — Interview: See a concise suggested answer, "avoid/do say" tips, and a bridge back to your pitch.

2) Requirements

FR1 — Ephemeral audio: in-memory only, discarded after Whisper processes it. Never written to disk.

FR2 — Short suggestions: one-liner (<= 140 chars), recommended response (1-2 sentences), 2-3 alternatives, next question, risk warnings.

FR3 — Profile-driven: load a YAML profile defining your objective, constraints, tone, key points. Quick-switch between profiles.

FR4 — Claude CLI as brain: spawn a fresh `claude` agent per session with profile compiled into system prompt. Feed it context, get suggestions.

FR5 — Local-only: local Whisper for STT, Claude CLI for coaching. No separate API keys, no cloud deployment.

FR6 — Zero persistence: no audio, no text, no logs, no history. Session end = everything gone.

NFR1 — Latency: speech → first suggestion on screen < 1.5-2.5s (Whisper runs every ~1-2s + Claude response).

NFR2 — Zero-footprint: only persisted files are your profile YAMLs.

3) Architecture

The entire app is a single Python process + a popup window.

┌──────────────────────────────────────────────┐
│  ng (single Python process)                  │
│                                              │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐ │
│  │  Audio    │──→│  Whisper  │──→│  Claude  │ │
│  │  Capture  │   │  (local)  │   │  CLI     │ │
│  │  (PyAudio)│   │  ephemeral│   │  agent   │ │
│  └──────────┘   └──────────┘   └──────────┘ │
│                                      │       │
│                               ┌──────▼─────┐ │
│                               │   Popup    │ │
│                               │  (overlay) │ │
│                               └────────────┘ │
└──────────────────────────────────────────────┘

Components:

a) Audio Capture — PyAudio for mic, ScreenCaptureKit (via pyobjc) for system audio on macOS. Streams raw audio into an in-memory ring buffer.

b) Local Whisper — faster-whisper processes a sliding window from the ring buffer every ~1-2 seconds (VAD-gated). Outputs ephemeral text context. Older audio is continuously discarded from the ring buffer.

c) Claude CLI Agent — a `claude` subprocess spawned at session start with a system prompt compiled from the profile YAML. Receives context via stdin, returns structured suggestion JSON. Fresh agent per session, killed on session end.

d) Popup Overlay — simple always-on-top window (Python tkinter, or PyQt/PySide for nicer look). Renders suggestion JSON: one-liner, alternatives, warnings.

Alternatively for the popup: a tiny Tauri/Electron shell if richer UI is needed later.

4) Audio Capture & Speaker Separation

Speaker separation is handled at the hardware level — no ML diarization needed:

Mic input = YOU (always). System audio output = THEM (always).

These are two physically separate audio streams, so speaker identity is known by definition.

Desktop (macOS):

Stream A (YOU): PyAudio with default mic input device

Stream B (THEM): ScreenCaptureKit audio-only capture (macOS 13+), or BlackHole virtual device as fallback

Works with earphones/AirPods: ScreenCaptureKit captures audio at the OS mixer level, BEFORE it's routed to any output device. It intercepts the app's audio stream (e.g., Zoom's output) directly from the system audio graph. So it doesn't matter what you're listening through — earphones, AirPods, speakers, or nothing. The capture is independent of the physical output path.

Each stream feeds into its own in-memory ring buffer (last ~30 seconds each). Older audio is continuously overwritten/discarded.

Permissions: mic permission + screen recording permission (for system audio capture).

Browser fallback (single stream):

If only mic is available (e.g., browser with speakerphone/open mic picking up both sides), a simple heuristic is used: your voice is louder/closer to the mic. Energy-based threshold separates "loud = you" from "quieter = them". Less reliable but functional for MVP.

5) Context Extraction (Local Whisper) — High Frequency

Use faster-whisper (Python, CTranslate2-based) for speed on Apple Silicon.

Processing strategy — two-stream sliding window, every ~1-2 seconds:

1. Two separate ring buffers hold the last ~30 seconds of audio each (mic = YOU, system = THEM).
2. Every ~1-2 seconds, Whisper processes each buffer's sliding window (last ~10-15 seconds).
3. VAD (Voice Activity Detection) via Silero VAD gates processing per stream — Whisper only runs on a stream when speech is detected in it.
4. Each Whisper pass produces two labeled context strings: [YOU]: "..." and [THEM]: "...". These overwrite the previous context. Audio outside the window is continuously discarded.

This gives near-continuous, speaker-labeled context updates during active conversation.

Latency budget (Apple Silicon M1 Pro or better):
- whisper-small: ~200-300ms to process a 10s window → can run every ~1s
- whisper-medium: ~400-600ms → can run every ~1-2s
- whisper-large-v3-turbo: ~600-900ms → can run every ~1.5-2s

Model recommendation:
- MVP: whisper-small or whisper-medium for fastest refresh (~1s cycles)
- Quality: whisper-large-v3-turbo if hardware allows (~1.5-2s cycles)
- Configurable via `--whisper-model` flag

Output: two labeled context strings per pass:
  [YOU]: "...what you said recently..."
  [THEM]: "...what they said recently..."
Held in Python variables, fed to Claude as labeled context, then overwritten by the next pass. Never touches disk.

6) Coaching Engine (Claude CLI Agent)

Session lifecycle:

1. User runs `./ng start --profile vc_pitch`
2. Script reads `profiles/vc_pitch.yaml`, compiles it into a system prompt
3. Spawns `claude` CLI as a subprocess with the system prompt
4. Every ~1-2 seconds (gated by VAD — only when speech detected), sends the labeled context to the agent:
   "[THEM]: {their_context}\n[YOU]: {your_context}\nGive me your coaching suggestions."
5. Claude returns structured JSON (see output format below)
6. On session end: agent subprocess is killed, all variables cleared

System prompt template (compiled from profile):

You are my personal negotiation coach. My goal: {goals.primary}.
Key points I must hit: {key_points}.
I must not reveal: {constraints.do_not_reveal}.
I must not commit to: {constraints.do_not_commit}.
My preferred tone: {tone.default}.
My preferred tactics: {preferred_moves}.

I will send you conversation context labeled [THEM] (the other party) and [YOU] (me).
Focus your suggestions on how I should respond to what THEY are saying.
Respond ONLY with a JSON object:
{
  "one_liner": "What to say next, <= 140 chars",
  "recommended": "1-2 sentence response",
  "alternatives": [
    {"label": "Collaborative", "text": "..."},
    {"label": "Assertive", "text": "..."},
    {"label": "Probing", "text": "..."}
  ],
  "next_question": "A calibrated question to ask",
  "avoid": ["Don't say X", "Don't concede Y"],
  "risk": "Brief risk warning or null"
}

Be concise. Every suggestion must be short and glanceable.

Output format

{
  "one_liner": "We deploy standardized models — no bespoke work.",
  "recommended": "The core is productized: we deploy directly into the customer warehouse with standardized models and we're already onboarding on the same playbook.",
  "alternatives": [
    {"label": "Collaborative", "text": "Let me walk you through the exact deployment steps — I think you'll see it's repeatable."},
    {"label": "Assertive", "text": "We've onboarded multiple customers on the same playbook. This scales like a product."},
    {"label": "Probing", "text": "What would you need to see to believe this scales like a product company?"}
  ],
  "next_question": "What's your biggest concern about scalability?",
  "avoid": ["Don't get defensive", "Don't mention custom work"],
  "risk": "Don't promise timeline yet."
}

Fully offline alternative (Ollama)

For zero-network operation, replace Claude CLI with Ollama running a local model:

ollama run llama3:8b --system "$(cat compiled_prompt.txt)"

Lower suggestion quality but 100% air-gapped. No data leaves the machine at all.

7) Negotiation Playbooks

Baked into the system prompt as tactical guidance:

Tactical empathy — labeling ("It sounds like..."), mirroring (repeat last 1-3 words as question), accusation audit

Calibrated questions — "How would you like us to approach...?", "What would need to be true for you to say yes?"

Anchoring & framing — set anchors only when profile allows, reframe price → value → risk

Process control — always surface next steps (meeting #2, due diligence, timeline)

These are included in the system prompt so Claude naturally weaves them into suggestions.

8) Profile System

Profiles stored as YAML files in `profiles/` directory.

Profile schema:
id: vc_pitch_lupe
name: "VC Pitch — Lupe Analytics"
mode: "VC_PITCH"

goals:
  primary: "Get to next meeting + secure interest"
  secondary:
    - "Position as category-defining analytics infra"
    - "Create urgency without sounding desperate"

constraints:
  do_not_reveal:
    - "Exact pilot pricing unless asked"
    - "Weaknesses in pipeline"
  do_not_commit:
    - "Custom features without timeline review"

tone:
  default: "calm, sharp, confident"
  if_skeptical: "curious, evidence-based, no defensiveness"
  if_aggressive: "firm, polite, boundary-setting"

key_points:
  - "Mobile UA data is fragmented; insights arrive too late"
  - "Big publishers solve with big analytics teams; others stuck with spreadsheets"
  - "Single source of truth in customer warehouse (no data movement)"
  - "Domain models + AI surfacing what works and what to do next"
  - "Pilot with [customer], second onboarded, third in pipeline"
  - "Target €30K MRR by July"

narrative_elevator_pitch: |
  Mobile developers spend millions on UA across Facebook, TikTok, Applovin — but they're flying blind...

preferred_moves:
  - "Ask calibrated questions to uncover decision process"
  - "Use labeling/mirroring on objections"
  - "Bridge back to traction + next steps"

At startup, the YAML is compiled into the system prompt template. That's the only "compilation" step.

9) UI — Minimal Popup

A small always-on-top window. Nothing else.

Layout:

┌─────────────────────────────────┐
│ ● NG — VC Pitch        [▶ ON]  │
├─────────────────────────────────┤
│                                 │
│ 💬 "We deploy standardized     │
│    models — no bespoke work."   │
│                                 │
│ ─────────────────────────────── │
│ Recommended:                    │
│ "The core is productized: we    │
│ deploy directly into the        │
│ customer warehouse..."          │
│                                 │
│ [Collaborative] [Assertive]     │
│ [Probing]                       │
│                                 │
│ Next Q: "What's your biggest    │
│ concern about scalability?"     │
│                                 │
│ ⚠ Don't promise timeline yet.  │
│ ✕ Don't get defensive.         │
└─────────────────────────────────┘

Hotkeys:

⌘+Space — show/hide popup

⌘+1/2/3 — copy alternative to clipboard

⌘+N — request fresh suggestion

⌘+Q — end session (destroys everything)

Click any suggestion to copy it to clipboard.

Implementation: Python tkinter (simplest) or PyQt6 (nicer). Can upgrade to Tauri later if needed.

10) Project Layout

Dead simple. No monorepo, no packages, no build system.

ng/
  ng.py              # main entry point — orchestrates everything
  audio.py           # mic + system audio capture (ring buffer)
  whisper_ctx.py     # local Whisper context extraction (sliding window, ~1-2s cycles)
  coach.py           # Claude CLI agent management
  popup.py           # always-on-top popup window
  profiles/
    vc_pitch_lupe.yaml
    salary_negotiation.yaml
  requirements.txt   # faster-whisper, silero-vad, pyaudio, pyobjc, pyyaml
  ng.md              # this spec

11) Run

# Install
pip install -r requirements.txt

# Start a session
python ng.py --profile vc_pitch_lupe

# That's it. Popup opens, listens, suggests. Ctrl+C or ⌘+Q to stop.

No .env file needed — Claude CLI uses its own auth. For Ollama fallback:

python ng.py --profile vc_pitch_lupe --engine ollama --model llama3:8b

12) Session Lifecycle

1. START: load profile YAML → compile system prompt → spawn Claude CLI agent → open popup → start audio capture + Whisper
2. RUNNING: audio ring buffer → Whisper extracts context every ~1-2s (VAD-gated) → context sent to Claude agent → suggestions displayed in popup → repeat
3. STOP (⌘+Q or Ctrl+C): kill Claude agent subprocess → clear all in-memory variables → close popup → exit process. Zero trace left.

13) Guardrails

Privacy: no disk writes of audio or text. Audio ring buffer is overwritten continuously. Context strings are Python variables, garbage collected on exit.

Content safety: system prompt instructs Claude to refuse unethical suggestions. No threats, no deception, no manipulation.

Code-level: no `open()` in write mode for audio/text, no database, no logging of conversation content.

14) MVP Milestones

Milestone A — Works (mic only, Claude CLI)

 audio.py captures mic via PyAudio
 whisper_ctx.py extracts context with faster-whisper
 coach.py spawns Claude CLI agent with compiled profile prompt
 popup.py shows suggestions in always-on-top tkinter window
 Zero persistence — everything ephemeral

Milestone B — System audio (hear both sides)

 ScreenCaptureKit integration for macOS system audio
 Combined mic + system audio context extraction

Milestone C — Polish

 Hotkeys (copy to clipboard, refresh, hide/show)
 Profile quick-switching from popup dropdown
 Ollama fallback for fully offline mode

15) Example

You're on a VC call. The investor says: "This feels like a services business."

Your popup instantly shows:

💬 "We deploy standardized models into customer warehouses — no bespoke work."

Recommended: "I understand the concern. The core is productized: we deploy directly into the customer warehouse with standardized models and we're already onboarding customers on the same playbook."

[Collaborative] "Let me walk you through the deployment steps — I think you'll see it's repeatable."
[Assertive] "We've onboarded multiple customers on the same playbook. This scales like a product."
[Probing] "What would you need to see to believe this scales like a product company?"

Next Q: "What's your biggest concern about scalability?"

⚠ Don't promise timeline yet.
✕ Don't get defensive. Don't mention custom work.

You glance, pick one, keep talking. The popup updates with each new exchange.
