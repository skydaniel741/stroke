"""CSS engine + deterministic training-plan generator (the Runna model,
swim-flavored).

Critical Swim Speed (CSS) is the pace a swimmer can hold for ~20-30 minutes,
measured with a 400m + 200m freestyle time-trial pair:

    CSS seconds per 100m = (T400 - T200) / 2

Every target time and send-off in a plan is derived from CSS via fixed zone
offsets, so a plan session reads like a coach wrote it for exactly this
swimmer: "8x100 FR target 1:32 on 1:45".

The generator composes named workouts from workout_templates.TEMPLATES into a
base -> build -> taper phase structure with scheduled deload weeks (the same
3-up-1-down wave swim_logic.next_week_target uses), a fixed weekly slot rhythm
(contents rotate so no two weeks repeat), and capped volume progression.

Everything here is deterministic math -- no AI. Imports FROM swim_logic,
never the reverse.
"""

import copy
import json
import math
from datetime import date, datetime, timedelta

from swim_logic import (
    BASE_PACE_100, DEFAULT_LEVEL, FITNESS_FACTOR, MIN_REST,
    MODIFIER_FACTOR, SESSION_CAP, STROKE_FACTOR, WEEK_CAP,
    START_VOLUME_PER_DAY, _age_factor, fmt_time, parse_time,
)
from workout_templates import get_template, templates_for

# ---------------------------------------------------------------------------
# CSS: compute, find, estimate
# ---------------------------------------------------------------------------

# Zone offsets in seconds per 100m relative to CSS (standard CSS scheme).
ZONE_OFFSETS = {
    'recovery': +12.0,
    'endurance': +6.0,
    'tempo': +2.0,
    'threshold': 0.0,
    'vo2max': -4.0,
}

# Sanity bounds on a believable CSS (sec/100m): faster than world-record-ish
# threshold pace or slower than 4:00/100m means bad input, not a real swimmer.
CSS_MIN, CSS_MAX = 55.0, 240.0

# Estimated CSS from the level pace model: threshold pace is a touch quicker
# than the sustainable-repeat pace BASE_PACE_100 describes.
EST_CSS_FACTOR = 0.95

# Extra rest baked into a send-off on top of the target swim, by zone.
# Recovery/technique reps get generous rest; threshold stays tight on purpose.
ZONE_REST_SLACK = {
    'recovery': 20.0,
    'endurance': 15.0,
    'tempo': 12.0,
    'threshold': 10.0,
    'vo2max': 30.0,  # speed work needs real recovery to stay fast
}


def compute_css(t400, t200):
    """CSS in seconds per 100m from a 400/200 time-trial pair, or None when
    the pair can't be trusted (mis-logged trials produce absurd paces)."""
    if not t400 or not t200:
        return None
    if t400 <= t200 * 1.9:  # a real 400 is meaningfully slower than 2x the 200
        return None
    css = (t400 - t200) / 2.0
    if not (CSS_MIN <= css <= CSS_MAX):
        return None
    return css


def find_time_trials(user_id, days=90, end=None):
    """The swimmer's fastest freestyle 400 and 200 from logged Swims in the
    `days`-long window ending at `end` (defaults to now). Returns
    (swim400, swim200) -- either may be None."""
    from models import Swim
    end = end or datetime.utcnow()
    cutoff = end - timedelta(days=days)
    swims = Swim.query.filter(Swim.user_id == user_id, Swim.logged_at >= cutoff, Swim.logged_at < end).all()
    best = {200: None, 400: None}
    for s in swims:
        if 'free' not in (s.event or '').lower():
            continue
        d = s.distance()
        if d not in best:
            continue
        secs = s.time_in_seconds()
        if not secs:
            continue
        if best[d] is None or secs < best[d].time_in_seconds():
            best[d] = s
    return best[400], best[200]


def estimate_css(profile):
    """Fallback CSS from the level pace model when no time trials exist.
    Rough by design -- the plan schedules a CSS test in week 1 to correct it."""
    level = getattr(profile, 'level', None) or DEFAULT_LEVEL
    age = getattr(profile, 'age', None)
    fitness = getattr(profile, 'fitness_ability', None) or 'Moderate'
    base = BASE_PACE_100.get(level, BASE_PACE_100[DEFAULT_LEVEL])
    css = base * _age_factor(age) * FITNESS_FACTOR.get(fitness, 1.0) * EST_CSS_FACTOR
    return min(max(css, CSS_MIN), CSS_MAX)


def zones(css):
    """The five training-zone paces (sec/100m) for a given CSS."""
    return {zone: css + off for zone, off in ZONE_OFFSETS.items()}


def target_seconds(dist, zone_pace100):
    """Target swim time for one rep. Linear on purpose: zone paces are already
    sustainable prescriptions, so no Riegel exponent here."""
    return zone_pace100 * dist / 100.0


def send_off(dist, zone_pace100, zone, level=None):
    """Send-off (interval) seconds: target swim + zone rest slack, respecting
    the level's minimum rest, rounded UP to :05 like a real pace clock.
    Slack scales with rep distance -- a 400 at threshold earns more wall time
    than a 50, even though threshold rest stays deliberately tight."""
    target = target_seconds(dist, zone_pace100)
    slack = max(ZONE_REST_SLACK.get(zone, 15.0), MIN_REST.get(level or DEFAULT_LEVEL, 10.0))
    slack *= max(1.0, dist / 200.0)
    return math.ceil((target + slack) / 5.0) * 5.0


def get_or_create_css(user_id, profile, pool='25m'):
    """The swimmer's current CssRecord: latest on file, else computed from
    recent time trials, else estimated from the level model. Persists (but
    does not commit) any newly created record."""
    from app import db
    from models import CssRecord
    rec = (CssRecord.query.filter_by(user_id=user_id)
           .order_by(CssRecord.recorded_at.desc()).first())
    if rec:
        return rec

    s400, s200 = find_time_trials(user_id)
    if s400 and s200:
        css = compute_css(s400.time_in_seconds(), s200.time_in_seconds())
        if css:
            rec = CssRecord(user_id=user_id, t400_seconds=s400.time_in_seconds(),
                            t200_seconds=s200.time_in_seconds(), css_per_100=css,
                            source='time_trial', swim_400_id=s400.id,
                            swim_200_id=s200.id, pool=s400.pool or pool)
            db.session.add(rec)
            return rec

    rec = CssRecord(user_id=user_id, css_per_100=estimate_css(profile),
                    source='estimated', pool=pool)
    db.session.add(rec)
    return rec


def css_is_stale(record, weeks=7):
    """A CSS older than ~7 weeks (or merely estimated) is due for a retest."""
    if record is None or record.source == 'estimated':
        return True
    return (datetime.utcnow() - (record.recorded_at or datetime.utcnow())).days >= weeks * 7


# ---------------------------------------------------------------------------
# Template resolution: zone placeholders -> real times for THIS swimmer
# ---------------------------------------------------------------------------

def resolve_template(template, css, level=None, age=None, fitness=None, target_meters=None):
    """Turn a workout template into concrete blocks for one swimmer: scale the
    main work toward target_meters, then bake each block's zone into a target
    time and send-off. Output blocks are the exact SavedSet.sets_data shape.

    CSS is a freestyle SWIM pace, so blocks with another stroke or a modifier
    (kick/drill/pull) get their zone pace scaled by the same stroke/modifier
    factors the generic pace model uses -- a kick 25 at "recovery" pace is a
    very different clock time than a freestyle 25.

    Deliberately NOT run through swim_logic.validate_day_blocks: that net
    judges send-offs with the generic level pace model, and a swimmer whose
    measured CSS is faster than their level's average would get their
    personalized targets "fixed" back to generic ones. Internal consistency
    (send-off = target + at least the level's minimum rest) holds by
    construction in send_off()."""
    blocks = copy.deepcopy(template['blocks'])
    scale_idx = template.get('scale_block_indexes') or []

    if target_meters and scale_idx:
        _scale_blocks(blocks, scale_idx, target_meters, level)

    z = zones(css)
    resolved = []
    for b in blocks:
        zone = b.pop('zone', None)
        rest_mode = b.pop('rest_mode', 'interval')
        rest_fixed = b.pop('rest_fixed', None)
        max_effort = b.pop('max_effort', False)
        dist = int(b.get('dist') or 0)
        note = b.get('note') or ''

        if max_effort:
            # Time-trial rep: no prescribed pace, explicit recovery after.
            b['rest'] = fmt_time(rest_fixed if rest_fixed is not None else 60)
            b['rest_type'] = 'rest'
        elif zone:
            pace = (z[zone]
                    * STROKE_FACTOR.get(b.get('stroke') or 'FR', 1.0)
                    * MODIFIER_FACTOR.get(b.get('modifier') or '', 1.0))
            target = target_seconds(dist, pace)
            if rest_mode == 'rest':
                b['rest'] = fmt_time(rest_fixed if rest_fixed is not None else
                                     max(MIN_REST.get(level or DEFAULT_LEVEL, 10.0), 20.0))
                b['rest_type'] = 'rest'
            else:
                b['rest'] = fmt_time(send_off(dist, pace, zone, level))
                b['rest_type'] = 'interval'
            # Easy swimming stays easy -- no clock target on recovery reps.
            if zone != 'recovery':
                tgt = f"target {fmt_time(target)}"
                note = f"{note} ({tgt})" if note else tgt
        b['note'] = note
        b['zone'] = zone if not max_effort else 'max'  # kept for UI chips; harmless extra key
        resolved.append(b)

    return resolved


def _scale_blocks(blocks, scale_idx, target_meters, level):
    """Nudge scalable blocks' reps up/down so the session total approaches
    target_meters, without butchering the workout's shape. Also respects the
    per-session cap for the level."""
    cap = SESSION_CAP.get(level or DEFAULT_LEVEL, 4000)
    target = min(target_meters, cap)

    def total():
        return sum(int(b.get('reps') or 0) * int(b.get('dist') or 0) * int(b.get('round_reps') or 1)
                   for b in blocks)

    # Grow: add reps round-robin across scalable blocks (max 2x original reps).
    originals = {i: int(blocks[i].get('reps') or 0) for i in scale_idx}
    guard = 200
    while total() < target * 0.9 and guard > 0:
        grew = False
        for i in scale_idx:
            b = blocks[i]
            if int(b.get('reps') or 0) < originals[i] * 2:
                if total() + int(b.get('dist') or 0) * int(b.get('round_reps') or 1) > target * 1.08:
                    continue
                b['reps'] = int(b.get('reps') or 0) + 1
                grew = True
            if total() >= target * 0.9:
                break
        if not grew:
            break
        guard -= 1
    # Shrink: trim reps (never below 1, and never below half the original).
    while total() > target * 1.1 and guard > 0:
        shrunk = False
        for i in sorted(scale_idx, key=lambda i: -(int(blocks[i].get('reps') or 0) * int(blocks[i].get('dist') or 0))):
            b = blocks[i]
            reps = int(b.get('reps') or 0)
            if reps > max(1, originals[i] // 2):
                b['reps'] = reps - 1
                shrunk = True
                break
        if not shrunk:
            break
        guard -= 1


# ---------------------------------------------------------------------------
# Plan generation
# ---------------------------------------------------------------------------

MIN_PLAN_WEEKS, MAX_PLAN_WEEKS = 4, 24
NO_RACE_WEEKS = 8  # rolling block ending in a CSS retest

# Fixed weekly slot rhythm by sessions/week (Runna model: the rhythm never
# changes, only the workout inside each slot rotates).
SLOTS_BY_COUNT = {
    1: ['threshold'],
    2: ['threshold', 'endurance'],
    3: ['technique', 'threshold', 'endurance'],
    4: ['technique', 'threshold', 'sprint', 'endurance'],
    5: ['technique', 'threshold', 'sprint', 'endurance', 'endurance'],
    6: ['technique', 'threshold', 'sprint', 'endurance', 'endurance', 'technique'],
    7: ['technique', 'threshold', 'sprint', 'endurance', 'endurance', 'technique', 'threshold'],
}

# Share of the week's meters each slot carries (normalized per plan).
SLOT_SHARE = {'technique': 0.20, 'threshold': 0.27, 'sprint': 0.18, 'endurance': 0.35, 'css_test': 0.27}

DEFAULT_DAYS = [0, 2, 4, 6]  # Mon/Wed/Fri/Sun


def _event_distance(event):
    import re
    m = re.match(r'\s*(\d+)', event or '')
    return int(m.group(1)) if m else 0


def build_phase_map(weeks, taper_weeks):
    """Per-week phase labels + deload flags. Base is the first ~40% of the
    pre-taper block, build the rest; deloads fall every 4th week (3-up-1-down,
    matching swim_logic.next_week_target) but never inside the taper."""
    pre_taper = weeks - taper_weeks
    base_weeks = max(1, round(pre_taper * 0.4)) if pre_taper > 1 else pre_taper
    phase_map = []
    for i in range(weeks):
        if i >= pre_taper:
            phase = 'taper'
        elif i < base_weeks:
            phase = 'base'
        else:
            phase = 'build'
        deload = phase != 'taper' and (i + 1) % 4 == 0
        phase_map.append({'phase': phase, 'deload': deload})
    return phase_map


def build_plan(user_id, profile, goal_event=None, pool='25m', race_date=None,
               target_time=None, sessions_per_week=3, preferred_days=None):
    """Generate and persist a full TrainingPlan with every PlannedSession.
    Marks any previous active plan abandoned. Returns the new plan (committed).

    Raises ValueError with a user-facing message when inputs can't make a plan.
    """
    from app import db
    from models import TrainingPlan, PlannedSession

    level = getattr(profile, 'level', None) or DEFAULT_LEVEL
    age = getattr(profile, 'age', None)
    fitness = getattr(profile, 'fitness_ability', None) or 'Moderate'

    sessions_per_week = max(1, min(int(sessions_per_week or 3), 7))
    slots = SLOTS_BY_COUNT[sessions_per_week]

    today = date.today()
    start_date = today + timedelta(days=(7 - today.weekday()) % 7 or 7)  # next Monday

    if race_date:
        weeks = math.ceil((race_date - start_date).days / 7)
        if weeks < MIN_PLAN_WEEKS:
            raise ValueError('That race is less than 4 weeks away, which is too short to build a proper plan. '
                             'Pick a later target date, or leave the date off for an 8 week block.')
        weeks = min(weeks, MAX_PLAN_WEEKS)
        taper_weeks = 2 if _event_distance(goal_event) <= 100 else 3
        taper_weeks = min(taper_weeks, max(0, weeks - 2))
    else:
        weeks = NO_RACE_WEEKS
        taper_weeks = 0

    phase_map = build_phase_map(weeks, taper_weeks)

    # Preferred days -> one date per slot per week.
    days = sorted({int(d) for d in (preferred_days or []) if 0 <= int(d) <= 6})
    for d in DEFAULT_DAYS + list(range(7)):
        if len(days) >= sessions_per_week:
            break
        if d not in days:
            days.append(d)
    days = sorted(days[:sessions_per_week])

    # CSS anchor.
    css_rec = get_or_create_css(user_id, profile, pool=pool)
    css = css_rec.css_per_100

    # Volume ladder.
    week_volumes = []
    vol = min(START_VOLUME_PER_DAY.get(level, 2200) * sessions_per_week, WEEK_CAP.get(level, 24000))
    last_full = vol
    for i, wk in enumerate(phase_map):
        if wk['phase'] == 'taper':
            remaining = weeks - i
            vol_i = last_full * (0.4 if remaining == 1 else 0.6 if remaining == 2 else 0.75)
        elif wk['deload']:
            vol_i = vol * 0.75
        else:
            if i > 0:
                vol = min(vol * 1.06, WEEK_CAP.get(level, 24000))
            vol_i = vol
            last_full = vol
        week_volumes.append(int(vol_i))

    # Which weeks hold a CSS test: week 0 when the CSS is only estimated,
    # then every ~7th week in a deload week, never during taper.
    test_weeks = set()
    if css_rec.source == 'estimated':
        test_weeks.add(0)
    last_test = 0 if test_weeks else -3  # estimated-CSS test counts as week 0
    for i, wk in enumerate(phase_map):
        if wk['phase'] != 'taper' and wk['deload'] and i - last_test >= 6:
            test_weeks.add(i)
            last_test = i
    if not race_date:
        # No race: the final week's quality session IS the retest (the "race").
        test_weeks.add(weeks - 1)

    # Normalize slot shares for this week rhythm.
    share_total = sum(SLOT_SHARE[s] for s in slots)

    # Mark any previous active plan abandoned.
    TrainingPlan.query.filter_by(user_id=user_id, status='active').update({'status': 'abandoned'})

    plan = TrainingPlan(
        user_id=user_id, goal_event=goal_event or None, pool=pool,
        race_date=race_date, target_time=target_time or None,
        start_date=start_date, weeks=weeks, sessions_per_week=sessions_per_week,
        preferred_days=json.dumps(days), css_record_id=None,
        phase_map_json=json.dumps(phase_map),
    )
    db.session.add(plan)
    db.session.flush()  # need plan.id and css_rec.id
    plan.css_record_id = css_rec.id

    last_key = {}  # slot -> previous week's template key, so weeks never repeat
    for w in range(weeks):
        wk = phase_map[w]
        for slot_i, slot in enumerate(slots):
            slot_here = slot
            # The CSS test replaces the week's threshold slot.
            if w in test_weeks and slot == 'threshold':
                slot_here = 'css_test'
            # Taper: endurance slots become shorter technique/tempo work.
            if wk['phase'] == 'taper' and slot == 'endurance':
                slot_here = 'technique'

            pool_templates = templates_for(slot_here, wk['phase'], level)
            if not pool_templates:  # fall back without phase filter
                pool_templates = templates_for(slot_here, None, level)
            idx = (w + user_id + slot_i) % len(pool_templates)
            template = pool_templates[idx]
            # Never serve the same workout in the same slot two weeks running
            # (possible when the phase changes and the pools differ in size).
            if len(pool_templates) > 1 and template['key'] == last_key.get(slot):
                template = pool_templates[(idx + 1) % len(pool_templates)]
            last_key[slot] = template['key']

            target_m = int(week_volumes[w] * SLOT_SHARE.get(slot, 0.25) / share_total)
            blocks = resolve_template(template, css, level=level, age=age,
                                      fitness=fitness, target_meters=target_m)
            total_m = sum(int(b.get('reps') or 0) * int(b.get('dist') or 0) * int(b.get('round_reps') or 1)
                          for b in blocks)

            db.session.add(PlannedSession(
                plan_id=plan.id, user_id=user_id, week_index=w,
                phase=wk['phase'], is_deload=wk['deload'], slot=slot_here,
                scheduled_date=start_date + timedelta(weeks=w, days=days[slot_i]),
                template_key=template['key'], title=template['name'],
                blocks_json=json.dumps(blocks), target_meters=total_m,
            ))

    db.session.commit()
    return plan


# ---------------------------------------------------------------------------
# Adaptive helpers (the non-punishing Runna behaviors)
# ---------------------------------------------------------------------------

def link_completed(user_id, session):
    """Called after a training Session is logged: if a plan session was
    scheduled within a day of it, mark that plan session completed. Best
    effort -- returns the PlannedSession or None, never raises to the caller's
    detriment (wrap the call site in try/except anyway)."""
    from app import db
    from models import PlannedSession, TrainingPlan
    plan = TrainingPlan.query.filter_by(user_id=user_id, status='active').first()
    if not plan:
        return None
    logged = (session.logged_at or datetime.utcnow()).date()
    ps = (PlannedSession.query
          .filter(PlannedSession.plan_id == plan.id,
                  PlannedSession.status == 'planned',
                  PlannedSession.scheduled_date >= logged - timedelta(days=1),
                  PlannedSession.scheduled_date <= logged + timedelta(days=1))
          .order_by(PlannedSession.scheduled_date)
          .first())
    if not ps:
        return None
    ps.status = 'completed'
    ps.completed_session_id = session.id
    ps.completed_at = datetime.utcnow()
    session.planned_session_id = ps.id
    db.session.commit()
    return ps


def sweep_missed(plan):
    """Mark stale planned sessions missed, and gently move THIS week's missed
    session forward to a free day in the same week (never across weeks --
    the plan absorbs a missed day instead of punishing it)."""
    from app import db
    from models import PlannedSession
    today = date.today()
    changed = False

    stale = (PlannedSession.query
             .filter(PlannedSession.plan_id == plan.id,
                     PlannedSession.status == 'planned',
                     PlannedSession.scheduled_date < today - timedelta(days=1))
             .all())

    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    week_dates = {ps.scheduled_date for ps in PlannedSession.query.filter(
        PlannedSession.plan_id == plan.id,
        PlannedSession.scheduled_date >= monday,
        PlannedSession.scheduled_date <= sunday).all()}

    for ps in stale:
        if monday <= ps.scheduled_date <= sunday:
            # Try to slide it to a free later day this week.
            moved = False
            d = max(today, ps.scheduled_date + timedelta(days=1))
            while d <= sunday:
                if d not in week_dates:
                    ps.scheduled_date = d
                    week_dates.add(d)
                    moved = True
                    changed = True
                    break
                d += timedelta(days=1)
            if not moved:
                ps.status = 'missed'
                changed = True
        else:
            ps.status = 'missed'
            changed = True

    if changed:
        db.session.commit()
    return changed


def rebuild_future_sessions(plan, css_record):
    """A new CSS landed (test, retest or manual entry): re-resolve target
    times and send-offs for FUTURE sessions only -- past weeks stay as they
    were swum. Commits."""
    from app import db
    from models import PlannedSession
    from models import AthleteProfile
    profile = AthleteProfile.query.filter_by(user_id=plan.user_id).first()
    level = getattr(profile, 'level', None) or DEFAULT_LEVEL
    age = getattr(profile, 'age', None)
    fitness = getattr(profile, 'fitness_ability', None) or 'Moderate'

    today = date.today()
    future = (PlannedSession.query
              .filter(PlannedSession.plan_id == plan.id,
                      PlannedSession.status == 'planned',
                      PlannedSession.scheduled_date >= today)
              .all())
    for ps in future:
        template = get_template(ps.template_key)
        if not template:
            continue
        blocks = resolve_template(template, css_record.css_per_100, level=level,
                                  age=age, fitness=fitness, target_meters=ps.target_meters)
        ps.blocks_json = json.dumps(blocks)
    plan.css_record_id = css_record.id
    plan.updated_at = datetime.utcnow()
    db.session.commit()
    return len(future)
