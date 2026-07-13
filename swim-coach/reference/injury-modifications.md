# Injury modifications

Always ask before prescribing dryland work — never assume "no injuries"
because none is on file. Injury status can change session to session in a
way STROKE's DB doesn't track (see SKILL.md `## What STROKE does NOT store`).

## Intake: check before every prescription

If `injury-status.md` doesn't exist, or is more than ~2 weeks old, ask in one
short message before designing the session:

1. Any current shoulder pain or discomfort (which side, sharp/dull, when it
   shows up — during specific strokes, overhead reaching, or at rest)?
2. Any knee pain, especially on the inside of the knee (breaststroke-related)?
3. Any lower back tightness or pain?
4. Anything else — wrist, hip, ankle — flagged by the athlete or their coach?

Save the answers to `injury-status.md` (edit in place, not append-only —
this is a current-status snapshot, not a log). Update it immediately
whenever new pain is reported, don't wait for the next scheduled check.

## Red flags — stop and refer, don't prescribe around it

If any of these come up, tell the athlete to stop dryland training (and flag
that they should mention it to their swim coach) and see a
physiotherapist/clinician. Do not offer a modification path for these —
they're outside this skill's lane:

- Sharp, sudden-onset pain (as opposed to dull/gradual ache)
- Numbness or tingling radiating down the arm or leg
- A joint that locks, catches, or gives way
- Pain that wakes the athlete at night
- Visible swelling, bruising, or deformity
- Pain that's worsening session over session despite rest

## Common swimmer injuries — modification paths

**⚠ FLAGGED FOR VERIFICATION** — the modification directions below are
general S&C/rehab-adjacent common sense (regress load, avoid the aggravating
range, keep the rest of the program moving), not a physiotherapy protocol.
Verify specifics — especially exact ranges of motion to avoid and return-to-
loading criteria — against AustSwim/current physio guidance before this goes
live. Nothing here should be read as clearing an athlete to train through
pain.

### Shoulder impingement / swimmer's shoulder

Very common given repetitive overhead, internally-rotated loading.

- **What to avoid:** overhead pressing through end-range, straight lateral
  raises above shoulder height, anything reproducing a pinching sensation at
  the top of the movement.
- **Modify toward:** scaption raises instead of lateral raises (lower
  impingement risk — see dryland-exercises.md), external rotation work kept
  pain-free range only, reduce overhead volume generally.
- **Keep training:** core and lower-body plyo work are usually still fine
  (confirm no loading through the shoulder, e.g. no overhead med ball
  catches) — don't shut down the whole session for a shoulder issue if the
  rest of the body is pain-free.
- **Progression back:** only add range/load back once the athlete reports
  pain-free through a full pain-free range for multiple sessions in a row —
  ⚠ verify a specific session/day count against physio guidance rather than
  using a vague "feels better."

### Breaststroker's knee (medial knee pain)

Common with high breaststroke volume, related to the whip-kick's valgus
loading pattern on the knee.

- **What to avoid:** deep loaded squats/lunges with knee valgus (knee
  caving inward), any explicit whip-kick-pattern dryland drills.
- **Modify toward:** squat and lunge variations with strict knee tracking
  over the toes, lower-impact plyo (broad jumps over box jumps), consider
  reducing breaststroke-specific dryland analogues entirely until resolved.
- **Keep training:** upper body and core work is usually unaffected — don't
  cut shoulder/core work for a knee issue.
- **Coordinate with the pool coach:** medial knee pain is often driven by
  in-pool breaststroke volume/technique, which is outside this skill's
  control — flag that a reduction in breaststroke kick volume in the pool
  may be needed alongside any dryland modification.

### Lower back tightness/pain

Common with butterfly and breaststroke's hyperextension pattern, and with
poor core control under fatigue.

- **What to avoid:** loaded spinal flexion/extension under fatigue,
  aggressive plyometric landing volume until resolved.
- **Modify toward:** anti-extension and anti-rotation core work (plank,
  dead bug, Pallof press) over flexion-based ab work, emphasize hip hinge
  mechanics if any loaded lower-body work is included.
- **Progression back:** as tightness resolves and pain-free range returns,
  reintroduce rotational core work before reintroducing plyo landing volume.

## After any modification

- Update `injury-status.md` with what's currently restricted and why.
- Note the modification in the session output itself (`**Notes:**` line in
  the dryland session shape from SKILL.md) so the athlete sees it was a
  deliberate choice, not a shortened/lazy session.
- Re-ask injury status at the next re-prescribe check-in (2-4 weeks) even if
  nothing new was reported in between — see SKILL.md
  `## Re-prescribe protocol`.
