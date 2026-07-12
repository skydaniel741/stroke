"""Deterministic swim science shared by the AI coach, the program builder and
the coach-side set generator.

Everything in here is plain math on well-understood swimming concepts -- no AI.
The three jobs:

1. Pace model: estimate how long a given swimmer actually takes to swim a rep
   (distance x stroke x modifier, adjusted for level, age and fitness).
2. Interval logic: an interval/send-off ("4x100 on 1:30") means the swimmer
   LEAVES every 1:30 -- rest is whatever is left after the swim, NOT 1:30.
   These helpers keep that distinction honest and catch impossible send-offs.
3. Progression: next week's target volume with progressive overload and a
   scheduled recovery week, instead of blindly increasing forever.
"""

import math
import re

# ---------------------------------------------------------------------------
# Time parsing / formatting
# ---------------------------------------------------------------------------

_TIME_RE = re.compile(r'^(?:(\d{1,3}):)?(\d{1,4})(?:\.(\d{1,2}))?$')

# Hard sanity bounds on any single rest/interval/swim time we handle.
MAX_TIME_SECONDS = 2 * 60 * 60  # nothing in a swim set is longer than 2 hours


def parse_time(value):
    """Parse 'M:SS', 'M:SS.xx', 'SS' or 'SS.xx' into seconds (float).
    Returns None for anything malformed, negative, non-finite or absurd --
    never raises. This is the one true time parser: '1e100', 'Infinity',
    'NaN', '-500' and friends all come back as None."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    m = _TIME_RE.match(s)
    if not m:
        return None
    mins = int(m.group(1) or 0)
    secs = int(m.group(2))
    frac = float(f'0.{m.group(3)}') if m.group(3) else 0.0
    if mins and secs >= 60:
        return None  # '1:75' isn't a time
    total = mins * 60 + secs + frac
    if not math.isfinite(total) or total <= 0 or total > MAX_TIME_SECONDS:
        return None
    return total


def fmt_time(seconds, hundredths=False):
    """Format seconds as 'M:SS' (or 'M:SS.xx'). Sub-minute stays '0:SS'."""
    if seconds is None or not math.isfinite(seconds) or seconds < 0:
        return ''
    if hundredths:
        return f'{int(seconds // 60)}:{seconds % 60:05.2f}'
    return f'{int(seconds // 60)}:{int(round(seconds % 60)):02d}'


# ---------------------------------------------------------------------------
# Pace model: what a rep realistically takes THIS swimmer
# ---------------------------------------------------------------------------

# Sustainable training pace in seconds per 100m freestyle, by level. These are
# repeat-set paces (what you can hold across a main set), not one-off race PBs.
BASE_PACE_100 = {
    'Beginner': 135.0,      # ~2:15/100m
    'Intermediate': 105.0,  # ~1:45/100m
    'Advanced': 88.0,       # ~1:28/100m
    'Competitive': 76.0,    # ~1:16/100m
}
DEFAULT_LEVEL = 'Intermediate'

# Relative cost of each stroke vs freestyle at the same effort.
STROKE_FACTOR = {'FR': 1.0, 'BK': 1.12, 'BR': 1.28, 'FL': 1.16, 'IM': 1.15}

# Kick sets are dramatically slower than swimming; drill work is deliberately
# slow; pull is roughly swim speed.
MODIFIER_FACTOR = {'': 1.0, 'Pull': 1.03, 'Kick': 1.55, 'Drill': 1.30, 'Snorkel': 1.05}

# Age adjustment: kids and masters swim training reps slower than a swimmer
# in their prime at the same "level" label.
def _age_factor(age):
    if not age:
        return 1.0
    if age < 10:
        return 1.40
    if age <= 12:
        return 1.20
    if age <= 15:
        return 1.06
    if age <= 39:
        return 1.0
    if age <= 54:
        return 1.06
    return 1.16


FITNESS_FACTOR = {'Low': 1.10, 'Moderate': 1.0, 'Good': 0.95, 'High': 0.90}


def estimate_rep_seconds(dist, stroke='FR', modifier='', level=None, age=None, fitness=None):
    """Best estimate of how long one rep takes this swimmer, in seconds.
    Uses a Riegel-style endurance curve so a 400 rep is paced slower per 100
    than a 50 rep."""
    try:
        dist = int(dist)
    except (TypeError, ValueError):
        return None
    if dist <= 0:
        return None
    base = BASE_PACE_100.get(level or DEFAULT_LEVEL, BASE_PACE_100[DEFAULT_LEVEL])
    pace100 = (
        base
        * _age_factor(age)
        * FITNESS_FACTOR.get(fitness or 'Moderate', 1.0)
        * STROKE_FACTOR.get(stroke or 'FR', 1.0)
        * MODIFIER_FACTOR.get(modifier or '', 1.0)
    )
    # Riegel endurance drift: pace per 100 slows as the rep gets longer
    # (and 25s/50s come out a touch quicker than the 100 pace).
    pace100 *= (dist / 100.0) ** 0.06
    return pace100 * dist / 100.0


# ---------------------------------------------------------------------------
# Interval vs rest: the critical distinction
# ---------------------------------------------------------------------------
#
#   4x100 on 1:30  ->  interval (send-off). You START every 1:30.
#                      Swim 1:15 -> you get 15 seconds of rest. Not 1:30.
#   4x100 w/ 30s   ->  rest. You get 30s between reps regardless of swim time.
#
# The minimum realistic rest inside a send-off: elite swimmers train on 5s
# rest (USRPT), developing swimmers need more.

MIN_REST = {'Beginner': 15.0, 'Intermediate': 10.0, 'Advanced': 5.0, 'Competitive': 5.0}

# A send-off that leaves more rest than this is just dead time on the clock.
MAX_SENSIBLE_REST = 240.0


def analyze_block(block, level=None, age=None, fitness=None):
    """Break one set block down into its real components.

    Returns a dict:
      est_swim   -- estimated swim time per rep (seconds)
      interval   -- the send-off time if rest_type == 'interval', else None
      rest       -- the ACTUAL rest per rep in seconds (interval - swim, or
                    the explicit rest), None if no rest info given
      realistic  -- False if the numbers don't physically work for this swimmer
      issue      -- human-readable problem description when realistic is False
    """
    reps = _safe_int(block.get('reps'))
    dist = _safe_int(block.get('dist'))
    if not reps or not dist:
        return {'est_swim': None, 'interval': None, 'rest': None, 'realistic': False,
                'issue': 'Missing reps or distance.'}

    est = estimate_rep_seconds(dist, block.get('stroke'), block.get('modifier'),
                               level=level, age=age, fitness=fitness)
    rest_secs = parse_time(block.get('rest'))
    rest_type = block.get('rest_type') if block.get('rest_type') in ('interval', 'rest') else (
        'interval' if reps > 1 else 'rest'
    )
    min_rest = MIN_REST.get(level or DEFAULT_LEVEL, 10.0)

    out = {'est_swim': est, 'interval': None, 'rest': None, 'realistic': True, 'issue': ''}
    if rest_secs is None:
        return out  # no rest info given: nothing to validate

    if rest_type == 'interval':
        out['interval'] = rest_secs
        implied = rest_secs - est
        out['rest'] = implied
        # The pace model is an estimate, so leave ~25% tolerance on the
        # minimum-rest check: a borderline-tight send-off (a real threshold
        # set) shouldn't get rewritten, only genuinely unmakeable ones.
        if implied < min_rest * 0.75:
            out['realistic'] = False
            if implied <= 0:
                out['issue'] = (
                    f"{reps}x{dist} on {fmt_time(rest_secs)} is impossible at this level: the swim "
                    f"alone takes about {fmt_time(est)}, so the swimmer can't make the send-off."
                )
            else:
                out['issue'] = (
                    f"{reps}x{dist} on {fmt_time(rest_secs)} leaves only ~{int(implied)}s rest "
                    f"(swim ~{fmt_time(est)}); this level needs at least {int(min_rest)}s."
                )
    else:
        out['rest'] = rest_secs
        # Explicit rest: the classic bad output is '200m with 20s rest' for a
        # beginner. Longer reps at lower levels need proportionally more
        # recovery; trained swimmers genuinely use very short rest.
        needed = min_rest
        if dist >= 200 and (level or DEFAULT_LEVEL) in ('Beginner',):
            needed = max(needed, est * 0.20)
        elif dist >= 200 and (level or DEFAULT_LEVEL) == 'Intermediate':
            needed = max(needed, est * 0.08)
        if reps > 1 and rest_secs < needed:
            out['realistic'] = False
            out['issue'] = (
                f"{reps}x{dist} with only {int(rest_secs)}s rest is unrealistic for this level "
                f"(each rep takes ~{fmt_time(est)}; needs at least {int(needed)}s recovery)."
            )
    return out


def fix_block(block, level=None, age=None, fitness=None):
    """Return (block, fix_note). If the block's interval/rest doesn't work for
    this swimmer, adjust it to the nearest realistic value (send-offs round up
    to the nearest 5 seconds, like real pace clocks). fix_note is None when
    nothing needed changing."""
    analysis = analyze_block(block, level=level, age=age, fitness=fitness)
    if analysis['realistic'] or analysis['est_swim'] is None:
        return block, None

    min_rest = MIN_REST.get(level or DEFAULT_LEVEL, 10.0)
    est = analysis['est_swim']
    fixed = dict(block)
    old = block.get('rest') or ''

    if (block.get('rest_type') or 'interval') == 'interval' or analysis['interval'] is not None:
        # Rebuild the send-off: swim time + a sensible rest (at least the level
        # minimum, or ~15% of the swim for longer reps), rounded up to :05.
        target_rest = max(min_rest, est * 0.15)
        new_interval = math.ceil((est + target_rest) / 5.0) * 5.0
        fixed['rest'] = fmt_time(new_interval)
        fixed['rest_type'] = 'interval'
        note = (f"Send-off adjusted from {old or '?'} to {fixed['rest']} "
                f"(swim ~{fmt_time(est)} + realistic rest).")
    else:
        needed = max(min_rest, est * (0.20 if (level or DEFAULT_LEVEL) == 'Beginner' else 0.10))
        new_rest = math.ceil(needed / 5.0) * 5.0
        fixed['rest'] = fmt_time(new_rest)
        fixed['rest_type'] = 'rest'
        note = f"Rest increased from {old or '?'} to {fixed['rest']} so the set is actually swimmable."
    return fixed, note


# Per-session and per-week volume that's sane for each level (metres).
SESSION_CAP = {'Beginner': 2200, 'Intermediate': 4000, 'Advanced': 6000, 'Competitive': 8000}
WEEK_CAP = {'Beginner': 11000, 'Intermediate': 24000, 'Advanced': 42000, 'Competitive': 65000}


def validate_day_blocks(blocks, level=None, age=None, fitness=None):
    """Validate and fix one day's blocks. Returns (fixed_blocks, notes).
    Fixes impossible intervals/rests, and trims volume if the day blows past
    what this level can sensibly swim in one session."""
    notes = []
    fixed_blocks = []
    for b in blocks or []:
        fb, note = fix_block(b, level=level, age=age, fitness=fitness)
        if note:
            notes.append(note)
        fixed_blocks.append(fb)

    cap = SESSION_CAP.get(level or DEFAULT_LEVEL, 4000)
    total = sum((_safe_int(b.get('reps')) or 0) * (_safe_int(b.get('dist')) or 0) for b in fixed_blocks)
    if total > cap:
        # Trim reps off the biggest main-set blocks until the day fits.
        # Never touch warm up / cool down.
        over = total - cap
        candidates = sorted(
            (b for b in fixed_blocks if b.get('section') in ('Main set', 'Sub set', 'Pre set')),
            key=lambda b: (_safe_int(b.get('reps')) or 0) * (_safe_int(b.get('dist')) or 0),
            reverse=True,
        )
        for b in candidates:
            if over <= 0:
                break
            dist = _safe_int(b.get('dist')) or 0
            reps = _safe_int(b.get('reps')) or 0
            if dist <= 0 or reps <= 1:
                continue
            cut = min(reps - 1, math.ceil(over / dist))
            b['reps'] = reps - cut
            over -= cut * dist
        new_total = sum((_safe_int(b.get('reps')) or 0) * (_safe_int(b.get('dist')) or 0) for b in fixed_blocks)
        if new_total < total:
            notes.append(
                f"Session trimmed from {total}m to {new_total}m; {total}m in one session "
                f"is too much for a {(level or DEFAULT_LEVEL).lower()} swimmer."
            )
    return fixed_blocks, notes


def validate_program(program, level=None, age=None, fitness=None):
    """Run every day of a generated weekly program through the realism checks.
    Mutates day blocks/totals in place; returns the list of fix notes."""
    all_notes = []
    for day in program.get('days', []):
        if day.get('rest'):
            continue
        fixed, notes = validate_day_blocks(day.get('blocks', []), level=level, age=age, fitness=fitness)
        day['blocks'] = fixed
        day['total'] = sum((_safe_int(b.get('reps')) or 0) * (_safe_int(b.get('dist')) or 0) for b in fixed)
        all_notes.extend(notes)
    return all_notes


# ---------------------------------------------------------------------------
# Progression engine: progressive overload with scheduled recovery
# ---------------------------------------------------------------------------

# Trend labels used across the app (athlete_model classifies into these).
TRENDS = ('improving', 'plateauing', 'regressing', 'overtraining', 'undertraining')

# Fresh-start weekly volume when there's no history to progress from, per
# level, per training day (the program builder multiplies by days/week).
START_VOLUME_PER_DAY = {'Beginner': 1200, 'Intermediate': 2200, 'Advanced': 3200, 'Competitive': 4200}


def next_week_target(last_week_volume, week_index, trend, level=None, days_per_week=3):
    """Target volume (metres) for next week plus the reasoning.

    week_index counts completed training weeks; every 4th week is a scheduled
    recovery week (~75% volume) regardless of trend, because progressive
    overload without deloads is how swimmers get injured.

    Returns {'volume': int, 'kind': str, 'why': str}.
    """
    level = level or DEFAULT_LEVEL
    days = max(1, min(int(days_per_week or 3), 14))
    floor = 600
    cap = WEEK_CAP.get(level, 24000)

    if not last_week_volume or last_week_volume < 500:
        vol = START_VOLUME_PER_DAY.get(level, 2200) * days
        return {
            'volume': int(min(vol, cap)), 'kind': 'baseline',
            'why': 'Not enough training history yet, so this week sets a sensible baseline for your level.',
        }

    if week_index > 0 and (week_index + 1) % 4 == 0:
        vol = last_week_volume * 0.75
        kind, why = 'recovery', (
            'Scheduled recovery week: volume drops about 25% so your body absorbs the last three '
            'weeks of work and injury risk stays low. Intensity stays light.'
        )
    elif trend == 'improving':
        vol = last_week_volume * 1.06
        kind, why = 'build', 'You have been improving consistently, so volume steps up about 6% this week.'
    elif trend == 'plateauing':
        vol = last_week_volume * 1.0
        kind, why = 'stimulus-change', (
            'Progress has flattened, so instead of more volume the plan changes the training stimulus: '
            'different intervals and set structures to give your body a new problem to solve.'
        )
    elif trend in ('regressing', 'overtraining'):
        vol = last_week_volume * 0.85
        kind, why = 'reduce', (
            'Recent signs point to accumulated fatigue, so volume comes down about 15% with more rest '
            'and a technique focus while you recover.'
        )
    elif trend == 'undertraining':
        vol = last_week_volume * 1.10
        kind, why = 'rebuild', 'Training has been lighter than planned lately, so this week rebuilds volume by about 10%.'
    else:
        vol = last_week_volume * 1.03
        kind, why = 'steady', 'Steady continuation with a small nudge in volume.'

    return {'volume': int(max(floor, min(vol, cap))), 'kind': kind, 'why': why}


def _safe_int(v):
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    return n if 0 < n < 100000 else None
