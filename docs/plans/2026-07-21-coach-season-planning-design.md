# Coach season/macrocycle planning — design

**Date:** 2026-07-21
**Status:** Design validated with user; not yet built.

## Problem

Schedule (`cpRenderSchedule`) plans one session at a time — there's no way for a coach to see where a squad sits in its season (base building vs. taper vs. race-ready), or how many weeks remain until a target meet. Nothing else in the coach section covers this: the performance-features roadmap ([2026-07-21-coach-performance-features-design.md](2026-07-21-coach-performance-features-design.md)) covers race pacing and readiness, not macrocycle structure.

## Scope decision (visual only, not automation)

Considered three levels of automation — visual timeline only, AI-assisted phase generator, full auto-scheduling. Picked **visual timeline only**: the coach lays out phases and a target meet as a reference overlay on top of the existing Schedule tab. No AI, no auto-generated sessions. Keeps this a cheap, low-risk addition rather than a second training-plan generator (that already exists for Solo swimmers via `plan_logic.py`).

## Data model

- One `SeasonPlan` per squad, stored as a JSON blob column (`season_plan_json`) on `Squad` — same lightweight pattern as `SavedSet.blocks` / `TrainingProgram.content_blocks`. New column needs a `migrate.py` entry per the project's migration rule.
- Shape: `{ targetMeet: { name, date }, phases: [{ phase, start, end }] }`.
- **Target meet name** — NZ-specific presets (NAGs, NZ Short Course Champs, NZ Short Course Open, NZ Long Course Champs, NZ Long Course Open, Club Champs) plus a custom-text option.
- **Phase** — reuses the *existing* `CP_AIGEN_PHASES` vocabulary already used by the "Generate with AI" panel (`static/js/coach_pro.js:1252`): Early season — base building / Mid season — quality / Taper — sharpen for racing / Post long-course transition, plus a custom-text option. One phase language across the whole coach section — no separate "Base/Build/Peak/Taper" taxonomy invented.
- Phases are an ordered list of date ranges; when a coach adds a new phase, its start date defaults to the day after the previous phase's end (removes manual date math without any AI involved).

## UI

**Placement:** a banner above the existing "Next session" card in the Schedule tab, with its own squad selector (Schedule shows a cross-squad event feed, so the plan needs to say which squad it's for — same selector pattern as Announcements' `cpAnnSquadSelect`).

**No plan yet:** a minimal empty-state strip — "No season plan set" + a "Set up season plan" button. Doesn't block normal Schedule use.

**Plan exists:** a dark strip (matching the existing `#111111`/`#ccccff` "Next session" card) showing:
- Target meet name + date, with a running "X weeks out" countdown
- Current phase as a colored pill
- A thin horizontal bar segmented by phase (proportional to date range) with a marker for today
- An edit icon opening the editor inline

**Editor** (same show/hide pattern as the set-builder's create-set form):
- Target meet: preset dropdown + date picker; "Custom" reveals a text input
- Phases list: phase-type dropdown (4 presets + custom) + start date + end date + remove button per row
- "Add phase" appends a row with the date-math default described above
- Save writes the whole `season_plan_json` blob in one call — no partial-phase endpoints

## Integration point (not required for v1, worth noting)

The "Generate with AI" panel already has a `season_phase` select using the same `CP_AIGEN_PHASES` values. Once the season plan exists, that dropdown could auto-select the squad's current phase instead of defaulting to the first option — a natural follow-up, not part of this build.

## Out of scope

- No auto-generated sessions from the phase plan (explicitly rejected — see Scope decision).
- No cross-squad season view — one plan per squad.
- No connection to the readiness/ACWR engine in this pass.
