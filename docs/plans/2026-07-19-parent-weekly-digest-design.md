# Parent weekly digest agent

Date: 2026-07-19
Status: Design validated (architecture + generation design both reviewed), not yet implemented.

## Problem

Coach side has zero autonomous/background agent behavior today — everything is either static computation or a manual "Analyze" click (AI Assistant tab, coach_pro.js ~566-654). Separately identified opportunity: a background job that drafts a personalized weekly update per parent (attendance, PBs, training), reusing the existing `ParentLink` infrastructure, rather than requiring the coach to write these by hand.

Other candidate background-agent ideas were considered and explicitly rejected as **not** needing an agent — standards-watch, injury-follow-up reminders, and overdue-assignment nagging are all pure SQL-threshold checks, not generation tasks. They belong as simple badges on the squad triage view (see the analytics-redesign design doc), not as separate agents. This digest is the one candidate that's genuinely LLM-shaped (turning structured data into readable prose is real generation work).

## Decisions made

- **Autonomy**: coach reviews and approves each draft before a parent ever sees it — not fully automatic. Rationale: an AI-drafted message reaching a parent with no human check is a hard-to-reverse mistake if the model gets something wrong or phrases it oddly; the review gate is cheap insurance.
- **Delivery channel**: no new email infrastructure. The app only has `send_verification_email` today (email_utils.py), nothing generic. Instead of building transactional email, the digest renders as a new card on the *existing* parent-facing page (`templates/parent_dashboard.html`, served by `routes_parent.parent_dashboard`) — only `status='approved'` rows are ever shown there.
  - Tradeoff acknowledged: this is pull, not push — a parent who doesn't habitually check that page won't see it, which undercuts the point of a "digest" somewhat. Decided to ship this simpler version first and instrument whether parents actually view it (e.g. a viewed/seen timestamp) before deciding whether real push (email) is worth building. Don't guess up front.
  - If a coach never visits the approval queue, the digest simply doesn't appear that week — no auto-approve fallback. This is intentional: an auto-approve escape hatch would quietly undermine the "review required" decision above.
- **Trigger**: this app has no scheduler at all (no APScheduler, no cron). Given deployment on Render, the fit is a **Render Cron Job** hitting a new internal route weekly, not an in-process scheduler thread (fragile under gunicorn's multi-worker model).

## Architecture

- **Trigger**: Render Cron Job → `POST /internal/digest/generate`, protected by a shared-secret header (not a user login — this is a service-to-service call).
- **Idempotency**: the route must skip any `parent_link_id` that already has a `draft`/`approved` row for the current `week_start`, so a retry or accidental re-run doesn't double-generate. Enforce via a unique constraint (see Data model), matching the existing `AttendanceRecord` pattern in this codebase (`uq_attendance_day` — same "one row per period" problem, same solution).
- **Review surface**: a small new queue in Coach Pro listing that coach's squads' draft digests; approving flips `status` to `approved` and the row becomes visible on the parent's dashboard.

## Data model

New `ParentDigest`:
- `id`
- `parent_link_id` (FK → `ParentLink`)
- `week_start` (Date)
- `content` (Text — see generation design below for actual shape)
- `status` ('draft' / 'approved')
- `generated_at`, `approved_at`
- `UniqueConstraint('parent_link_id', 'week_start')`

## Generation design

Follows this codebase's established pattern exactly: every existing generation path (`generate_coach_set`, `generate_checkin_insight`) uses a **forced tool call** (`tool_choice` pinned to a specific tool), never freeform text completion — this digest does the same, then runs the result through the same `_humanize()` post-processor everything else uses (the em-dash/AI-cliché scrubber).

**Prompt inputs**: swimmer name; this week's attendance count vs. the swimmer's own typical rate (not a generic squad average — already computed in `swimmer_payload`); whether this was a scheduled-but-skipped week vs. no session scheduled at all (via `CoachAssignment`/`SquadEvent`, so a bye week doesn't read as a bad week); any new PBs (event, time, improvement); optional coach-set tone.

**Output shape** (tool schema, e.g. `write_parent_digest`): `headline` (one sentence — the single most relevant thing this week), `body` (2-4 sentences), optional `next_up` (upcoming squad event, if any). Mirrors the existing `summary`/`likely_cause` split already used in `PROGRESS_INSIGHT_TOOL_SCHEMA` — gives the coach review queue distinct fields to scan instead of one undifferentiated paragraph.

**Low/negative-week handling** (the one failure mode specific to this feature): the prompt must include an explicit rule, not rely on tone alone — e.g. *"If attendance was low or there's nothing notable this week, do not manufacture positivity or imply concern; state what happened plainly and let the coach's own judgment carry any real concern in person."* Plus a direct reminder even though it's a global style rule elsewhere: *"A slower back half or a single off day is normal, not a red flag — never frame it as one."* This prompt is a new, separate call path and won't inherit house style automatically just because other prompts in the app follow it.

## Error handling

- Cron route: per-`parent_link_id` failures (Claude API error, malformed tool output) should not abort the whole batch — log and skip that one link, continue the rest.
- Same never-raise contract as other `ai_utils.py` functions.

## Testing

- Unique-constraint/idempotency test: running the generate route twice for the same week should not create duplicate rows.
- A test asserting `status='draft'` rows never appear in `routes_parent.parent_dashboard`'s rendered output, only `approved` ones.
- A low-week fixture (zero attendance, no PBs) asserting the generated content doesn't read as alarmed or falsely upbeat (likely a manual/eyeball check initially, not easily automated).
