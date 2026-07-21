# Evidence-based performance measures for the coach section — research

**Date:** 2026-07-21
**Purpose:** Move the coach section beyond race times toward the *determinants* of
improvement — applied physiology, swimming economy, stroke mechanics, and
swimming-specific force/power. The organising question is not "what's the best
science" but "which evidence-based measure can a coach actually feed STROKE
without a lab or a load cell." Each measure below is tagged by data cost.

## The core identity everything hangs off

Swimming velocity = **stroke rate (SR) × stroke length (SL)**. Race time is the
*output*; SR, SL, the aerobic engine, economy, and force are the *inputs* a coach
moves. Tracking only the output tells you *whether* a swimmer improved, not *why*.

---

## 1. Applied physiology — the aerobic engine

**The science.** Endurance is bounded by the maximal lactate steady state (MLSS)
— the highest intensity sustainable without lactate accumulating. Mean speed in
800/1500 m races sits ~3.4% above MLSS workload, and MLSS workload strongly
predicts individual performance. The lab measure needs an incremental blood-lactate
step test.

**The practical proxy: Critical Swim Speed (CSS).** CSS is the field-test stand-in
for threshold — "the swimming equivalent of FTP in cycling." It comes from two
maximal time trials:

> **CSS pace per 100 m = (T400 − T200) / 2** (a 400 m and a 200 m all-out, ≥10 min rest between)

From one CSS number you generate training pace zones coaches actually use:
recovery (65–75%), endurance (75–90%), threshold (90–100%), VO2max (100–110%).
Re-test every 4–8 weeks to track the engine growing.

**Honest caveat.** CSS is *not* identical to MLSS — studies show it tends to
overestimate the true steady-state speed, so treat it as a practical training
anchor, not a lab-exact threshold. Still the accepted field measure.

**Data cost: ZERO new data type.** STROKE already logs swim times. Two tagged time
trials → CSS → pace zones. This is the single highest-leverage addition.

## 2. Swimming economy — how much energy per metre

**The science.** Economy is energy cost C (kJ/m) = total energy expenditure ÷ pace.
Elite propelling efficiency is 46–77%, but *total* mechanical efficiency is only
5–8%, so small economy gains matter. Energy cost rises with stroke rate and
coordination index and falls with stroke length. True C needs oxygen-uptake
measurement — lab only.

**The practical proxy: Stroke Index (SI).**

> **SI = velocity × distance-per-stroke × cycle multiplier** (×2 for free/back, ×1 for fly/breast)

Higher SI = more distance per unit effort. It must be read *against stable split
times*: if pace holds but SI rises, the stroke genuinely got more economical.
Competitive freestyle SI averages ~3.06 (range ~1.2–4.9).

**Data cost: one number per rep (stroke count).** velocity comes from time we
already have; DPS = pool length ÷ strokes-per-length. A light "strokes" field on a
logged rep unlocks SI.

## 3. Stroke mechanics — the SR/SL profile

**The science.** From velocity = SR × SL, elite swimmers don't maximise either in
isolation — they hold the *optimal combination for the event*. Benchmarks: elite
freestyle DPS ~2 m+ (≈12–15 strokes/25 m); SR ~65–85 cycles/min for 100 m,
lower (60–75) for 400 m, 90+ for pure sprint. Recent work explicitly challenges the
old "always maximise stroke length" coaching cue for distance events.

**Coaching use.** Plot a swimmer's SR–SL point against faster swimmers' profiles and
train toward the gap (more SL here, higher SR there), rather than chasing one number.

**Data cost: same one number (stroke count) + time.** SL = pool ÷ strokes;
SR = strokes ÷ time. Same input as SI, different view.

## 4. Swimming-specific force / power

**The science.** In-water **tethered force** predicts sprint strongly: tethered
force correlates r = −0.66 to −0.84 with 50–100 m time, and 76% of 50 m time is
predicted by tethered force alone. **Dryland power** also correlates well (r =
0.51–0.83): lat-pulldown propulsive power (ρ ≈ 0.68), max strength, jumps,
med-ball. A *combination* of dryland power + in-water tethered force explains ~80%
of 50 m variance.

**Data cost, split two ways:**
- **Tethered in-water force → out of scope.** Needs a load cell / tether rig most
  clubs don't own. Document as a future integration, don't build.
- **Dryland power → feasible now.** STROKE already has a dryland module. Track a
  few high-correlation benchmarks (lat-pulldown power, vertical jump, med-ball
  throw) over time, and flag when dryland strength climbs but in-water speed
  doesn't (a transfer problem worth a coach's attention).

---

## What STROKE should build, in order

| Tier | Feature | Data cost | Reuses |
|---|---|---|---|
| **A (do first)** | **CSS test + auto pace zones + re-test tracking** | none — two tagged time trials | `pacing.py`, the set builder (prescribe sets *at* CSS pace) |
| **B** | Stroke Index + SR/SL profile per swimmer | one "strokes" number per logged rep | Athlete Hub, the split logger |
| **C** | Dryland power benchmarks vs in-water speed | dryland test numbers | existing dryland module |
| **Out** | Tethered in-water force; lab VO2/lactate | load cell / lab | — document only |

**The standout: Critical Swim Speed.** It is real, published physiology; it needs
only two swim times STROKE already captures; it outputs the pace zones coaches use
daily; it plugs straight into the set builder (every generated set can carry a
"% CSS" target) and the pacing engine already shipped. It turns STROKE from "we
record your races" into "we measure your engine and prescribe against it."

**A guardrail for all of the above.** Present these as *training-performance*
measures, not medical or physiological diagnosis. CSS is a training anchor, SI is a
technique signal — frame them as coaching tools, consistent with the readiness
panel's "not medical advice" line.

## Sources

- Critical Swim Speed vs MLSS: [PubMed 16195984](https://pubmed.ncbi.nlm.nih.gov/16195984/), [MLSS determines performance (Frontiers)](https://www.frontiersin.org/journals/physiology/articles/10.3389/fphys.2021.668123/full)
- CSS formula, zones, re-test cadence: [TrainingPeaks CSS guide](https://www.trainingpeaks.com/blog/how-to-use-critical-swim-speed-training/), [Top End Sports CSS test](https://www.topendsports.com/testing/tests/critical-swim-speed.htm)
- Swimming economy / efficiency: [Factors affecting swimming economy (PubMed)](https://pubmed.ncbi.nlm.nih.gov/15243747/), [propelling efficiency & energy cost (Springer)](https://link.springer.com/article/10.1007/s00421-008-0822-7)
- Stroke Index definition, ranges, coaching use: [TritonWear — Stroke Index](https://blog.tritonwear.com/interpreting-to-improving-stroke-index)
- SR/SL dynamics in elite freestyle: [Frontiers — SR–SL KDE](https://www.frontiersin.org/journals/sports-and-active-living/articles/10.3389/fspor.2025.1656633/full)
- Force/power & tethered swimming: [Dry-land F–V, P–V & swimming-specific force (PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC10443377/), [tethered swimming correlational analysis (PubMed)](https://pubmed.ncbi.nlm.nih.gov/26669251/)
