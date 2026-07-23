# CSS training-pace zones + swimmer-type classifier (coach Athlete Hub)

2026-07-24. Extends the CSS engine already built for the Solo training-plan
feature (`plan_logic.py`) and the existing coach-side "Aerobic capacity (CSS)"
card, which previously only showed a single pace number and required a
literal 400m + 200m freestyle time-trial pair.

## What prompted this

Danny wants a swimmer who PBs a distance (e.g. 400 free) to get an
AI-calculated breakdown of their training pace zones ("easy speed", "lactate
threshold", "max") without needing to log a second specific time trial.

## Decisions made

1. **Single-swim / any-pair CSS estimate.** True CSS needs a 400 and 200
   freestyle time trial (`CSS/100 = (T400 - T200) / 2`). When a swimmer is
   missing one or both, the system now Riegel-predicts the missing target(s)
   from whichever freestyle distance they *do* have logged (50/100/200/400/
   800/1500), using the same extrapolation guard (0.25x-4x) the existing PB
   time-predictor uses. Tagged `source: 'estimated_riegel'` vs. `'time_trial'`
   for a real pair, so the coach can see which they're looking at. No target
   reachable within a trustworthy ratio -> no estimate shown (honesty over a
   wild guess).
2. **Surface: coach Athlete Hub only**, next to the existing CSS card. Not
   solo (closed product), not a parent/self-swimmer view (a separate, larger
   project, intentionally parked as a follow-up -- see below).
3. **No set-builder hookup in this pass.** Zones are read-only display for
   now; wiring "prescribe this set at 90% CSS" into the set builder is a
   follow-up once coaches are actually using the zones panel.
4. **Zone labels** (five zones already existed as offsets in `plan_logic.
   ZONE_OFFSETS`): Recovery, Endurance, Tempo, Threshold, VO2max, each with a
   short coach-facing note. "Max" in Danny's original ask maps to VO2max, an
   aerobic zone -- not raw sprint speed, which is a different metric already
   covered by Personal Bests / Race Pacing.
5. **Swimmer-type classifier (sprint / balanced / distance-leaning).** Built
   in the same pass, using only freestyle PBs already logged, no new data.
   Fits each swimmer's own pace-vs-distance curve (least-squares in log-log
   space) and compares the exponent to the population Riegel exponent (1.06).
   Needs >= 2 freestyle PBs spanning a >= 3x distance gap to be trustworthy.
   Surfaces as its own small card next to the CSS card.

## Parked as a follow-up (explicitly, not forgotten)

A new read-only "self swimmer" layout for squad swimmers (distinct from the
existing coach-invited parent portal, and distinct from the closed Solo
product) was raised mid-brainstorm. Deliberately scoped out of this change --
it's its own project (new routes/templates/permissions, needs its own design
pass). The parent portal (`routes_parent.py` / `parent_dashboard.html`)
already exists; there's no squad-side "self swimmer" equivalent yet.

## What shipped

- `swim_logic.py`: `RIEGEL_EXPONENT` constant + `riegel_predict()`, a shared
  helper (also now used by the pre-existing PB time-predictor in `routes.py`,
  deduplicating what used to be an inline formula there).
- `plan_logic.py`: `css_estimate()` (generalized CSS, any freestyle pair),
  `ZONE_META` / `ZONE_ORDER` (coach-facing zone labels), `classify_swimmer_type()`
  + `SWIMMER_TYPE_LABELS` / `SWIMMER_TYPE_NOTES`. The existing `find_time_trials`
  / `compute_css` / `estimate_css` (profile-based, no-swims-at-all fallback)
  and their Solo training-plan call sites are untouched.
- `routes_coach.py`: `_css_trend` now calls `css_estimate` and returns the
  five zone paces + an estimated/real badge; new `_swimmer_type()` wired into
  `swimmer_payload` as `swimmerType`.
- `coach_pro.js`: `cpCssTrendPanel` now renders the zone breakdown table and
  an "ESTIMATED" badge + basis note when applicable; new `cpSwimmerTypePanel`.
- `test_systems.py`: coverage for `riegel_predict`'s extrapolation guard,
  `css_estimate` across a real pair / single distant swim / no trustworthy
  anchor, and `classify_swimmer_type`'s sprint/distance/insufficient-spread
  cases.
