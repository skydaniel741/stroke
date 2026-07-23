"""Split (pacing) analysis, shared by the solo swimmer analytics page and the
coach Athlete Hub so the split-science thresholds live in exactly one place.

The calibration here matters: in a raced distance the first 50 carries the
dive/push (roughly half a second of free speed) and fatigue builds through the
race, so a SMALL positive split (back half a touch slower) is the normal,
well-paced outcome, not a fault. A true negative split (faster back half) is
genuinely hard and a mark of excellent pacing. So we only flag a real problem
when the drop-off is large. Don't "fix" this to punish every positive split.
"""

import re


def parse_secs(t):
    """Parse a 'mm:ss.xx' or 'ss.xx' time string to seconds, or None."""
    if not t:
        return None
    t = str(t).strip()
    try:
        if ':' in t:
            mins, rest = t.split(':', 1)
            return int(mins) * 60 + float(rest)
        return float(t)
    except (ValueError, TypeError):
        return None


def fmt_secs(secs):
    if secs is None:
        return '—'
    if secs >= 60:
        return f'{int(secs // 60)}:{secs % 60:05.2f}'
    return f'{secs:.2f}'


def event_distance(event):
    m = re.match(r'\s*(\d+)', event or '')
    return int(m.group(1)) if m else 0


# Fade is (back-half avg - front-half avg) / front-half avg, as a percentage.
# The thresholds are the canonical split-science calibration (see module docstring).
PATTERN_LABELS = {
    'negative': 'Negative split',
    'even': 'Well paced',
    'normal-fade': 'Normal fade',
    'big-fade': 'Big back-half fade',
}

# Swimmer-facing (second person) -- what the solo analytics page shows.
SWIMMER_NOTES = {
    'negative': ("Negative split, you actually came home faster. That's genuinely hard to do and a sign of "
                 "great pacing and aerobic strength. Most swimmers can't, so this is a real strength."),
    'even': ("Well paced. The back half being a touch slower is completely normal (your first 50 has the "
             "dive), so this is strong, controlled pacing."),
    'normal-fade': ("A normal amount of fade for the distance, and some of it is just the dive advantage on your "
                    "first 50. Holding a little more through the back half is where your next bit of time is."),
    'big-fade': ("Big drop-off in the back half. That usually means you went out too fast for your current "
                 "fitness. Try starting a touch more controlled, your back half will thank you."),
}

# Coach-facing (about the swimmer) -- what the Athlete Hub shows.
COACH_NOTES = {
    'negative': ("Came home faster than they went out. Excellent pacing and aerobic strength, this is a genuine "
                 "asset, most swimmers can't do it."),
    'even': ("Well paced. A slightly slower back half is normal given the dive on the first 50, so this is "
             "controlled, mature pacing."),
    'normal-fade': ("A normal amount of fade for the distance. Their next time is in holding the back half a "
                    "little better, worth a controlled-back-half set."),
    'big-fade': ("Big back-half drop-off. Reads as going out too fast for current fitness. A more controlled "
                 "front half or some race-pace back-half work is the lever."),
}


def classify_fade(fade):
    """Map a fade percentage to a pattern key. Canonical thresholds."""
    if fade <= -0.5:
        return 'negative'
    if fade <= 3:
        return 'even'
    if fade <= 7:
        return 'normal-fade'
    return 'big-fade'


def analyze_splits(raw_splits):
    """Turn a list of 50m split strings into a pacing analysis, or None if
    there aren't at least two parseable splits. Returns the math + pattern only;
    callers attach a note via SWIMMER_NOTES / COACH_NOTES in their own voice."""
    secs_list = [v for v in (parse_secs(x) for x in (raw_splits or [])) if v is not None]
    if len(secs_list) < 2:
        return None
    n = len(secs_list)
    max_s = max(secs_list)
    bars = [
        {'idx': i + 1, 'secs': round(v, 2), 'label': fmt_secs(v), 'h': round(v / max_s * 100)}
        for i, v in enumerate(secs_list)
    ]
    half = n // 2
    first = secs_list[:half]
    second = secs_list[-half:]
    first_avg = sum(first) / len(first)
    second_avg = sum(second) / len(second)
    fade = (second_avg - first_avg) / first_avg * 100 if first_avg else 0
    pattern = classify_fade(fade)
    return {
        'bars': bars,
        'first_avg': fmt_secs(first_avg),
        'second_avg': fmt_secs(second_avg),
        'fade_pct': round(fade, 1),
        'pattern': pattern,
        'label': PATTERN_LABELS[pattern],
    }


def analyze_swims(swims, limit=5, voice='coach'):
    """Run analyze_splits over the most recent swims that carry splits, newest
    first. Attaches event/date/time and a note in the requested voice. `swims`
    are Swim rows (need .get_splits(), .event, .time, .logged_at)."""
    notes = COACH_NOTES if voice == 'coach' else SWIMMER_NOTES
    ordered = sorted(swims, key=lambda s: s.logged_at, reverse=True)
    out = []
    for s in ordered:
        analysis = analyze_splits(s.get_splits())
        if not analysis:
            continue
        analysis['event'] = s.event
        analysis['time'] = s.time
        analysis['date'] = s.logged_at.strftime('%d %b %Y')
        analysis['note'] = notes[analysis['pattern']]
        out.append(analysis)
        if len(out) >= limit:
            break
    return out
