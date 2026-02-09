# Profiles Context

YAML profiles in `profiles/` define negotiation/pitch parameters.

## Schema
See `ng.md` Section 8 for the full schema. Key fields:
- `id`, `name`, `mode`
- `goals.primary`, `goals.secondary[]`
- `constraints.do_not_reveal[]`, `constraints.do_not_commit[]`
- `tone.default`, `tone.if_skeptical`, `tone.if_aggressive`
- `key_points[]`
- `narrative_elevator_pitch`
- `preferred_moves[]`
- `special_context` (optional, investor-specific info)

## Available profiles
- `vc_pitch_42cap.yaml` — 42CAP pitch with Julian von Fischer context, Adverity differentiation, tough question responses
- `vc_pitch_lupe.yaml` — Generic Lupe Analytics VC pitch
