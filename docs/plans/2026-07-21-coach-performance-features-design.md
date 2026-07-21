# Coach performance features — design

**Date:** 2026-07-21
**Status:** Tier 0 flagship (Race Pacing) built; rest is the roadmap.

## Problem

The coach dashboard already measures *activity* well (attendance, volume, PB list, the athlete-model trend/load engine). What it does not do yet is help a coach read *performance*: how a swimmer paces a race, where their next time is, and how to feed the dashboard richer race data without hand-typing at a meet.

## Guiding decision: where race data comes from

Three ways to get performance data in, weighed for a solo first-year build that needs adoption over vanity:

- **Only what's logged now** (times, 50m splits, attendance, sessions). Zero friction, ships now. The 50m splits are underexploited and carry real coaching signal. *This is the bulk of Tier 0.*
- **Light in-meet manual entry** (stroke counts, tempo, turns). High value if adopted, but the moment of capture is a coach running eight lanes at a meet. This is where swim apps overbuild and coaches ignore it. **Deferred (Tier 2), documented not built.**
- **Import meet results files.** Cheaper than it looks because the roster CSV importer (shipped 2026-07-21) already exists. Extend it to results. Official, accurate, no in-meet typing. *Tier 1.*

## Tier 0 — Mine existing splits (no new data)

All computed over the existing `Swim` table; nothing new to type.

1. **Race Pacing (BUILT).** For each recent race with 50m splits: split-bar shape, front-half vs back-half average, back-half fade %, and a calibrated pattern (negative / well-paced / normal-fade / big-fade) with a coach-voice note. Calibration lives in `pacing.py` and is deliberately tolerant of small positive splits (the first 50 has the dive; a small fade is normal, not a fault). Shared with the solo swimmer analytics page so both read splits identically.
2. **PB progression.** Per-event time-vs-date line with PBs marked, so plateaus are visible at a glance. (The athlete-model trend engine already backs part of this.)
3. **Projected times.** Surface the existing Riegel predictions as "based on their 100, their 200 projects to X" so a coach spots events a swimmer underperforms relative to their own engine.
4. **Standards benchmarking.** Compare each time to age-group standard times (a static table loaded once) to show distance to the next qualifying tier. NZ-specific data; lowest priority, may defer.

## Tier 1 — Meet results importer (reuses the roster importer rail)

Same drag-drop + AI-column-mapping flow as the roster importer, pointed at a meet results export. Coach drops the file; a new `map_results_columns` (sibling of `map_roster_columns`) maps swimmer name / event / time / splits / date; the app matches each row to an existing squad swimmer **with a confirm step** (never auto-attach a race to the wrong swimmer), then bulk-creates `Swim` rows tagged `meet` with splits in the same JSON format the pacing engine reads.

The payoff: imported races immediately feed every Tier 0 feature. Tier 1 and Tier 0 meet in the `Swim` table without either knowing about the other. The Swimming NZ data-partnership pitch is the long-game version of this same pipe.

## Tier 2 — Deferred (documented, not built)

Manual per-race stroke entry (stroke count, tempo, turn times). On record as a known future option with the adoption-risk caveat, explicitly out of scope so it does not creep into v1.

## Recovery / readiness (BUILT alongside Tier 0)

A **Readiness & Load** panel in the Athlete Hub, framed as training-load
management, not medical or injury advice (the legal-veto guard). It fuses two
signals the athlete model already computes:

- **ACWR** (acute:chronic workload ratio) → load status: detraining / in range / ramping / spiking, on a bar centred at the swimmer's own 1.0x normal.
- **Check-in trend** (energy / fatigue / sleep, last 14 days vs the prior 14) when the swimmer self-reports; a graceful "load only" fallback when they don't (most coached squad swimmers won't).

These combine into one verdict — Ease off / Room to build / Good to push — plus
a plain coach recommendation. Thresholds mirror `athlete_model.classify_trend`
so the coach view and the solo trend engine never disagree. Pure client-side
synthesis of `swimmer_payload.athleteState`; no backend or DB change.

## What was built in this pass

- `pacing.py` — canonical split analysis: `parse_secs`, `fmt_secs`, `event_distance`, `classify_fade` (the calibrated thresholds), `analyze_splits`, `analyze_swims`. Single source of truth for the split-science rule.
- `routes_solo.py` — the solo analytics split block refactored onto `pacing.py` (behavior preserved, swimmer-voice notes intact).
- `routes_coach.py` — `swimmer_payload` now returns `pacingAnalyses` (coach voice) per swimmer.
- `static/js/coach_pro.js` — `cpPacingPanel` (Race Pacing) and `cpReadinessPanel` (Readiness & Load) in the Athlete Hub.

Verified end-to-end: analyzer unit tests pass, solo analytics unchanged, coach pacing panel renders real races (well-paced 1% fade and big-fade 10.7% classified correctly), readiness panel renders all branches (detraining/room-to-build, spiking+fatigued/ease-off, in-range/good-to-push).

## Follow-ups

- Tier 0 items 2–4 (progression chart, projected-time surfacing, standards table).
- Tier 1 results importer once Tier 0 is in coaches' hands.
- Stale test fixture: `test_systems.py::test_http` needs its solo user marked `solo_paid` (4 pre-existing failures unrelated to this work).
