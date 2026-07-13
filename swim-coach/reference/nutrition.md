# Nutrition

Meal/macro guidance tied to **training phase** and **today's actual session
load** — not a static diet plan. Pull phase from `AthleteProfile` if it's
tracked there, or ask; pull today's pool load from `Session.sets_data` /
`recompute_state()['weekly']`.

**Disclaimer:** this is general sports-nutrition guidance, not an
individualized dietetic prescription. For any athlete flagged as a minor
(`AthleteProfile.age` <18), with disordered-eating risk noted in
`limitations`, or with a medical condition, keep guidance to meal *structure
and timing* — skip specific calorie/macro numbers and recommend a registered
sports dietitian.

## Framing by training phase

| Phase | Volume | Nutrition emphasis |
|---|---|---|
| Base | Moderate-high volume, aerobic focus | Consistent carb intake to support volume; this is where eating habits get built, not a time to under-fuel |
| Build | Volume + intensity both up, peak training load | Highest carb needs of any phase — this is when under-fueling shows up fastest as flat performance or illness/injury risk |
| Taper | Volume drops, intensity holds | Total intake comes down roughly with volume (don't keep peak-phase calorie intake through a taper), but **don't cut carbs on quality/race-pace days** — protein and fat can trend down more than carbs |

## Carb timing around pool sessions

**⚠ FLAGGED FOR VERIFICATION** — the ranges below are general
endurance-sport sports-nutrition guidance adapted to swimming; verify
against current sports-dietitian guidance, especially for age-group/junior
swimmers where absolute numbers should be more conservative and framed as
"eat enough," not precise g/kg targets.

- **Pre-session (2-3h before a high-volume or high-intensity session):**
  carb-forward meal, moderate protein, lower fat/fibre (easier on the gut
  before hard swimming). E.g. oats + banana + honey, or rice + chicken +
  light sauce.
- **Close to session (30-60 min before, if needed):** small, fast-digesting
  carb — toast + jam, a banana, a sports drink. Skip if the athlete trains
  well fasted and reports no issues; don't force a pre-session snack that
  isn't needed.
- **During (only for genuinely long sessions, 90+ min continuous):**
  carbohydrate drink if the session is long/hard enough to warrant
  mid-session fueling — most age-group sessions don't need this, don't
  over-engineer it.
- **Post-session recovery window (within ~30-60 min of getting out):** carbs
  + protein together — this is the single highest-leverage nutrition timing
  point for a swimmer training multiple times a week, because it drives
  glycogen resynthesis and muscle repair before the next session. E.g.
  chocolate milk + a banana, a protein shake + fruit, or a full meal if
  timing allows (yogurt + fruit + granola, eggs on toast).

## High-volume pool day vs light/rest day

- **High-volume or double-session day:** bias carbs up across the whole day,
  not just around the session — this is the day-to-day version of the
  base/build phase emphasis above.
- **Light or rest day:** carbs can trend down somewhat, protein holds steady
  (recovery still happening), fat can be a slightly larger share of intake.
  Don't crash-diet a rest day — it's for recovery, not restriction.
- **Two-a-day (AM + PM sessions):** the gap between sessions is a critical
  refuel window — treat the AM post-session meal as seriously as end-of-day
  recovery, since the PM session starts from whatever glycogen state that
  meal leaves them in.

## Meal structure (framing, not a rigid template)

- Most swimmers training 5-6×/week do well with 3 meals + 1-2 snacks,
  timed around training rather than fixed clock times.
- Protein at each meal (supports recovery across multiple weekly sessions,
  not just post-workout).
- Hydration: swimmers chronically under-recognize their own sweat loss
  because they're already wet and don't feel thirsty the way a runner does —
  flag this explicitly. Water/fluids at every meal, plus deliberate
  hydration around sessions, not just "drink when thirsty."

## What NOT to do

- Don't hand a swimmer (especially a minor) a strict calorie deficit/surplus
  target — that's outside this skill's lane; if body composition goals come
  up, redirect to a sports dietitian and keep this skill's guidance to
  performance fueling and timing.
- Don't prescribe supplements beyond the basics (creatine, protein as a
  convenience tool, vitamin D if flagged low) unless asked, and never to a
  minor without flagging that a parent/guardian and clinician should be in
  the loop.
- Don't ignore reported eating-habit flags. `AthleteProfile.eating_habits`
  may already flag `undereating` or `skip_meals` — if so, lead with "are you
  eating enough, especially around sessions" rather than macro precision.

## Conflicting-goals note

If an athlete asks for both "eat less" and "hit peak training load this
block," surface the conflict the same way Personal-trainer-skill does for
lifting goals: under-fueling during build/peak phase directly costs
performance and raises injury/illness risk — it's not a free tradeoff.
Reframe toward "fuel the training you're doing" rather than a deficit during
a high-load phase, and offer to revisit intake once volume drops in taper or
off-season if body composition is still a goal then.
