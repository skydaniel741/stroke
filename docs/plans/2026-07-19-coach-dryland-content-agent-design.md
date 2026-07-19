# Coach-side dryland content-fetch agent

Date: 2026-07-19
Status: Design validated, not yet fully specced (sections below cover what's decided; implementation should confirm the storage/assignment details flagged as open).

## Problem

Coaches have no way to source dryland/conditioning content today. `generate_coach_set()` (ai_utils.py ~1156) only generates pool swim sets (categories: Fast/Easy/Heart Rate/Drill/Lactate/Fitness/Open Water/Triathlon — all swim-specific). A separate `TrainingProgram` library (models.py:424) already holds curated Strength/Mobility/Core content, but it's solo-only — no coach route or UI touches it.

## Decision: live web search, not the existing curated library

The lower-risk default would have been to reuse the existing `TrainingProgram` catalog (same pattern as `generate_training_program`: pick from a curated list, never invent). **The user explicitly chose live web search instead**, accepting the higher risk (unverified sources, potential injury-risk content, hallucination, cost) for fresher/more varied material. Sources requested: university/research papers (many swim-specific S&C papers are open-access), YouTube tutorials, and other known public programs.

Given that choice, the mitigations below (allowlist, mandatory review, age-range parameter) are load-bearing, not optional — this is the one place in the app's AI features where output isn't grounded in a pre-vetted catalog.

## Architecture

- **Trigger**: on-demand only, coach-initiated. Lives in Coach Pro's Session Builder area, as a sibling action to the existing "AI generate set" button (coach_pro.js ~566-654) — e.g. "Find dryland content."
- **Tier**: Claude API + tool use (web_search_20260209 + web_fetch_20260209 server tools), not Managed Agents — this is a bounded, single-turn-ish task that completes within one request, not a long-running autonomous session.
- **New route**: `POST /pro/api/dryland/search`, same shape as existing coach AI routes (`@login_required`, `@coach_required`, gated on `AI_SCAN_ENABLED`, never raises — returns `{'ok': False, 'error': ...}` on failure).
- **New ai_utils.py function**: `fetch_dryland_content(params, api_key, model)`, mirroring `generate_coach_set`'s shape. `params` includes: focus (e.g. "shoulder prehab for sprinters"), age_range (explicit parameter — youth vs. senior dryland recommendations differ meaningfully on safety grounds, this must not be inferred), squad/swimmer level.
- **Tools**: `web_search_20260209` with `allowed_domains` restricted to a curated allowlist (university/research sources, known reputable S&C/swimming organizations, specific YouTube channels if a channel-level allowlist is feasible) rather than the open web. `web_fetch_20260209` to pull page content for extraction. Note: `web_fetch` returns page HTML/text, not video transcripts — YouTube results will surface via title/description/channel metadata, useful for pointing a coach at a video, not for extracting exercise detail directly from it.
- **Output**: structured via a forced tool call (same pattern as every other generation path in this codebase), returning 1-3 candidate dryland sessions with source citations, not a single "best answer" — the coach picks.

## Data model & review flow

- Nothing is saved or assigned automatically. Results are ephemeral (returned in the API response, not persisted) until the coach explicitly clicks "Save" on a specific candidate.
- **Open item for implementation**: what a saved candidate becomes. Two options, decide during implementation:
  1. A new `TrainingProgram` row with `created_by=<coach's user id>` (distinct from the admin-seeded solo catalog, which presumably has `created_by=NULL` or a specific admin) — reuses the existing model/shape.
  2. A new coach-scoped table if mixing coach-fetched and admin-curated rows in the same table proves confusing.
  Either way, assigning a saved dryland item to a squad/swimmer needs either extending `CoachAssignment` (currently `saved_set_id` only references `SavedSet`) or a separate lightweight assignment path — not decided yet, out of scope for this design pass.

## Safety guardrails

- `allowed_domains` restriction on `web_search` (not open web).
- Mandatory human review before anything is saved — never auto-assign directly to a squad or swimmer.
- Explicit `age_range` parameter passed into the prompt, not inferred, so results are age-appropriate by construction rather than by the model guessing from context.
- A visible disclaimer on results ("AI-sourced from the web — review before assigning") in the UI.

## Error handling

Same contract as `generate_coach_set`: API failures, empty/malformed tool results, or a zero-candidate search all return a friendly `{'ok': False, 'error': ...}` rather than raising — never a raw 500 to the coach.

## Testing

- Unit test the allowlist enforcement (a search result outside `allowed_domains` should never surface).
- Unit test the age-range parameter is present in every generated prompt (regression guard against it being silently dropped in a refactor).
- No coach-route tests exist at all currently (see the analytics-redesign design doc's testing section) — this route should be included in whatever coach-route test scaffolding gets built first.
