# Load management — combined pool + dryland

STROKE already computes a pool-only acute:chronic workload ratio (ACWR) in
`athlete_model.recompute_state()`:

```python
acute = 7-day pool distance (Session.total_distance() + Swim.distance())
chronic_weekly = 28-day pool distance / 4
acwr = acute / chronic_weekly
```

That's distance-based (meters), and it's **pool-only**. Dryland has no
comparable DB-tracked number. The brief asked for a single combined ACWR —
**⚠ this doesn't cleanly exist in the literature.** Pool distance (meters)
and dryland session load (RPE × duration, a unitless-ish score) aren't the
same currency, and forcing them into one blended ratio would hide which
discipline is actually driving the risk. Instead this file uses **two
parallel load signals reconciled through a guardrail table** — check both,
let the more conservative one win. Flag this design choice for your own
review; it's a reasonable engineering call, not a cited standard.

## Signal 1: pool ACWR (already computed, don't rebuild it)

Read `state['acwr']` from `recompute_state(user_id)`. STROKE's own
`classify_trend()` already flags:

- `acwr >= 1.7` → overtraining (load spiking fast)
- `acwr >= 1.35` + high fatigue/low feeling check-ins → overtraining
- `acwr <= 0.55` (with meaningful chronic volume) → undertraining

Use these exact thresholds — they're already in production, don't invent
different pool cutoffs for this skill.

## Signal 2: dryland session load

Since there's no DB table, compute this from `dryland-log.md` entries (see
SKILL.md `## Data sources`). For each logged session:

```
session_load = RPE (1-10) × duration_minutes
```

This is the same `session_load` concept used by the claude-fitness-cn
reference skill for running — borrowed here for dryland instead.

- **Dryland acute load** = sum of `session_load` over the last 7 days.
- **Dryland chronic weekly load** = sum over the last 28 days, divided by 4.
- **Dryland ACWR** = acute ÷ chronic weekly (same math as the pool number,
  applied to a different unit — don't compare the two numbers to each other
  directly, only within their own history).

If fewer than ~2 weeks of dryland log entries exist, there isn't enough
chronic baseline to compute a meaningful ratio — say so and fall back to
simple rules (don't jump load week-over-week by more than ~20-30% in total
session_load; **⚠ verify this ramp-rate figure**, it's adapted from general
S&C ramp-rate guidance, not swim-specific).

## Reconciling the two signals

Don't average them into one number. Use whichever signal is more
conservative to gate today's dryland prescription:

| Pool ACWR | Dryland ACWR / trend | Today's dryland call |
|---|---|---|
| Normal (0.55-1.35) | Normal or no data yet | Full session — all three categories, standard volume |
| Normal | Elevated (dryland load spiking) | Back off dryland specifically — dryland is the thing driving risk, not the pool. Cuff/core only, skip plyo. |
| Elevated (≥1.35) or overtraining flag | Any | Back off regardless of dryland's own trend — the pool is already loading the same shoulders/legs. Light cuff/core activation only, skip plyo, keep it short. |
| Undertraining (≤0.55) | Normal | Fine to progress dryland load if the athlete wants — the ceiling isn't the dryland side |
| Undertraining | Also low/no recent dryland | Flag the conflict: is this a deliberate recovery block, a taper, or has the athlete just gone quiet on both fronts? Ask rather than assume. |

**Same-day check, not just weekly:** always ask (or check the log) whether
the athlete had a hard pool session *today or yesterday* before prescribing
plyometric work specifically — plyo stacked on top of a same-day hard water
session is the most common way to accidentally overload a swimmer, even if
the weekly ACWR numbers look fine. This is the brief's core "combined load"
requirement — the guardrail table handles the weekly trend, this check
handles the daily collision.

## Progression rules (when things are going well)

- **Cuff/core work**: progress by adding reps within the prescribed range
  before adding load. These are endurance/stability categories — chasing
  heavy load defeats the purpose (⚠ verify against current cuff-training
  literature, see dryland-exercises.md).
- **Plyometric work**: progress by moving down the progression order in
  dryland-exercises.md (bilateral → unilateral → reactive), not by adding
  volume to the current tier. More sets of squat jumps isn't the goal;
  advancing complexity is.
- **Never progress dryland load in the same week the pool ACWR is elevated**,
  even if the dryland numbers alone would support it.

## Recovery week structure

Every 3-4 weeks, or sooner if 2+ of: pool ACWR overtraining flag, dryland
ACWR spiking, check-in fatigue trending up 3+ days, reported joint pain —
drop dryland to cuff/core maintenance only (skip plyo entirely) for one week,
regardless of what the pool program is doing that week. This mirrors the
"deload sooner if flagged" pattern from Personal-trainer-skill, adapted to
gate on the combined pool+dryland picture rather than lifting-specific
signals like RIR.
