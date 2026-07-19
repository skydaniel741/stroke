# Coach-side performance analytics & squad triage redesign

Date: 2026-07-19
Status: Design validated, not yet implemented.

## Problem

Multi-agent review (backend-architect, code-reviewer, test-engineer, fullstack-developer) of the current coach-side "view swimmer performance" experience found:

- Solo athletes get a full progression/trend analytics engine (`athlete_model.py`, `/solo/analytics`) — plateau/regression detection, ACWR load tracking, split analysis. Coaches get none of this for the swimmers they actually coach: just a flat PB list and one 8-week volume bar chart (coach_pro.js Athlete Hub drawer, ~line 1104-1207).
- No proactive "who needs attention" surfacing beyond a plain "inactive ≥5 days" list (Team Analytics tab, coach_pro.js ~1211-1284).
- Two real bugs, independent of the redesign:
  - **IDOR**: `squad_swimmer_note` and `squad_swimmer_status` (routes_coach.py ~1318, ~1430) never verify the target swimmer belongs to the coach's squad.
  - **PB pool conflation**: personal-best calculation keys `best_by_event` by event only, not `(event, pool)`, in 4 places (routes_coach.py ~134, ~1120, ~1354, ~1515) — a 50m-pool time can silently overwrite/beat a 25m-pool PB.
- Zero test coverage on any coach route (`test_systems.py` never touches `routes_coach.py`).
- No indexes on `Swim.user_id`/`logged_at`, `Session.user_id`/`logged_at`, `AttendanceRecord.swimmer_id` — fine at current scale, flagged for later.

## Decisions made

- **Scope**: both per-swimmer progression analytics AND squad-level triage, as one integrated effort (not sequential separate features) — the architecture naturally supports both from the same cached state.
- **Bug fixes**: done first, separately, before the redesign work (cheap, independent, and the redesign would otherwise inherit the pool-conflation bug into new trend charts).
- **Per-swimmer progression view**: replaces the existing Athlete Hub drawer content in place (same entry point coaches already use) rather than a new full-page view.
- **Squad triage**: rebuilds the existing Team Analytics tab (already has the "inactive swimmers" list to build on) rather than a new tab, and rather than embedding flags directly in the Roster table.
- **Monetization**: reusing the Digital Athlete Model engine for coach-viewed (non-Solo-paying) swimmers is acceptable — Coach Pro is a separate revenue line from the individual Solo subscription, and richer analytics is a selling point for clubs adopting the platform. No gating needed.

## Architecture

- Drop the "solo-only" framing on `AthleteState`/`athlete_model.recompute_state()` — make it computable and cacheable for any `user_id`, not just Solo-tier accounts.
- `coach_pro_state()` (routes_coach.py ~56-297) stops re-scanning every `Swim`/`Session` row per squad per request; instead reads the cached `AthleteState` row per swimmer (already tolerant of ~24h staleness, refreshed on new-swim/session write). This changes the cost from O(squad_size × history) to O(squad_size).
- Squad-level triage becomes an aggregation over the same cached per-swimmer states — no new heavy queries, just reading rows that already exist for the progression view.
- Add missing indexes (`Swim.user_id`, `Swim.logged_at`, `Session.user_id`, `Session.logged_at`, `AttendanceRecord.swimmer_id`) while touching these models.
- Consolidate the 4 duplicated PB/recent-activity implementations into one shared helper (fixing the pool-conflation bug in one place, not four).
- Delete the dead `squad_swimmer_profile()` route and `coach_swimmer_profile.html` template (confirmed unreachable — only linked from the already-dead `squad_roster.html`).

## Components

1. **Bug-fix pass** (separate, first): pool-aware PB keying + shared helper; IDOR fix on the two note/status routes; delete dead route+template.
2. **Athlete Hub drawer redesign**: replace the flat PB list + single volume bar chart with per-event trend lines, plateau/regression flags, and load tracking — sourced from the swimmer's `AthleteState`, same content shape the solo analytics page already renders, just surfaced in the coach's existing drawer UI.
3. **Team Analytics rebuild**: ranked "needs attention" list — regressing, plateaued, attendance-dropping, standards-close — computed from the squad's set of cached `AthleteState` rows, replacing the current "inactive ≥5 days" + "top by distance" lists.

## Data flow

Swim/Session write → `update_athlete_state(user_id)` (existing solo trigger, now called regardless of tier) → cached `AthleteState` row → coach's `coach_pro_state()` reads the row (no live rescans) → Athlete Hub drawer renders it per-swimmer; Team Analytics aggregates it per-squad.

## Error handling

- Missing/stale `AthleteState` for a swimmer (e.g. never computed yet): fall back to "not enough data yet" in the drawer rather than erroring, matching the existing "No swims logged yet" pattern already used in this UI.
- IDOR fix: 404 (not 403) on a swimmer-not-in-squad mismatch, consistent with the rest of `routes_coach.py`'s existing `_squad_or_404` convention.

## Testing

Currently zero coverage on coach routes. Needs, before/alongside this work:
- A `_mk_squad`/`_mk_membership` test helper and a coach-role user fixture (none exist today — `test_systems.py`'s `_mk_user`/`_seed_swims` helpers don't cover squads at all).
- A regression test seeding the same event at both 25m and 50m, asserting the PB shown is pool-correct (this specific bug would not have been caught by any existing test).
- An IDOR test: coach A queries/writes against a swimmer in coach B's squad, asserting 404.
- A basic `coach_pro_state()` integration test once the AthleteState-backed path exists, asserting it doesn't rescan raw Swim/Session rows (can be checked via query-count assertion if the test harness supports it, or just via response shape).
