"""The digital athlete model: a persisted, per-swimmer performance profile
that every logged workout, swim and check-in updates, so the AI coach reasons
about long-term progression instead of treating each workout independently.

Three layers, all deterministic math (the AI only narrates on top):

- recompute_state / update_athlete_state: rebuild the swimmer's evolving
  profile (load, trends, PBs, recovery, consistency) and classify them as
  improving / plateauing / regressing / overtraining / undertraining.
- ensure_weekly_report: every 7 days, an automatic full review comparing this
  week against previous weeks -- progress score, PB improvements, strengths,
  weaknesses, consistency, recovery, confidence, suggested focus.
- adaptation_context: turns the state + progression engine into concrete
  instructions for the AI program builder, so difficulty actually adapts.
"""

import json
import logging
from datetime import datetime, timedelta

import swim_logic

logger = logging.getLogger(__name__)


def _fmt_secs(secs):
    if secs is None:
        return 'n/a'
    if secs >= 60:
        return f'{int(secs // 60)}:{secs % 60:05.2f}'
    return f'{secs:.2f}'


# ---------------------------------------------------------------------------
# State recomputation (PART 1 + PART 8: the models that learn from every log)
# ---------------------------------------------------------------------------

def recompute_state(user_id):
    """Rebuild the athlete state dict from the swimmer's full history.
    Pure read + math; the caller persists it."""
    from app import db
    from models import Swim, Session, CheckIn, AttendanceRecord

    now = datetime.utcnow()
    swims = db.session.query(Swim).filter_by(user_id=user_id).order_by(Swim.logged_at.asc()).all()
    sessions = db.session.query(Session).filter_by(user_id=user_id).all()

    # --- weekly volume, last 9 weeks (current partial week last) ---
    week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    weekly = []
    for i in range(8, -1, -1):
        ws = week_start - timedelta(weeks=i)
        we = ws + timedelta(days=7)
        vol = (
            sum(s.total_distance() for s in sessions if ws <= s.logged_at < we)
            + sum(s.distance() for s in swims if ws <= s.logged_at < we)
        )
        count = sum(1 for s in sessions if ws <= s.logged_at < we) + sum(1 for s in swims if ws <= s.logged_at < we)
        weekly.append({'week_start': ws.date().isoformat(), 'vol': vol, 'sessions': count})

    # --- training load: acute (7d) vs chronic (28d avg), the standard
    # acute:chronic workload ratio used to flag over/under-training ---
    acute = (
        sum(s.total_distance() for s in sessions if s.logged_at >= now - timedelta(days=7))
        + sum(s.distance() for s in swims if s.logged_at >= now - timedelta(days=7))
    )
    chronic_total = (
        sum(s.total_distance() for s in sessions if s.logged_at >= now - timedelta(days=28))
        + sum(s.distance() for s in swims if s.logged_at >= now - timedelta(days=28))
    )
    chronic_weekly = chronic_total / 4.0
    acwr = round(acute / chronic_weekly, 2) if chronic_weekly > 0 else None

    # --- per-event time trends (recent half vs earlier half) ---
    by_event = {}
    for s in swims:
        secs = s.time_in_seconds()
        if secs is not None:
            by_event.setdefault(s.event, []).append(secs)  # oldest -> newest

    events = {}
    for event, times in by_event.items():
        if len(times) < 4:
            continue
        half = len(times) // 2
        earlier_avg = sum(times[:half]) / half
        recent_avg = sum(times[-half:]) / half
        change_pct = (recent_avg - earlier_avg) / earlier_avg * 100 if earlier_avg else 0
        direction = 'improving' if change_pct < -0.4 else 'slipping' if change_pct > 0.4 else 'steady'
        events[event] = {
            'recent_avg': round(recent_avg, 2),
            'change_pct': round(change_pct, 2),
            'direction': direction,
            'n': len(times),
        }

    # --- PBs with recency, keyed by (event, pool) -- a 50m-pool time and a
    # 25m-pool time for the same event aren't comparable, so keying by event
    # alone let one silently overwrite (or lose to) the other. Key is a plain
    # string ("event|pool") rather than a tuple since this dict gets
    # json.dumps'd for persistence, and JSON object keys must be strings. ---
    pbs = {}
    for s in swims:
        secs = s.time_in_seconds()
        if secs is None:
            continue
        pool_key = '50' if str(s.pool or '25').startswith('50') else '25'
        key = f'{s.event}|{pool_key}'
        cur = pbs.get(key)
        if cur is None or secs < cur['secs']:
            pbs[key] = {
                'event': s.event, 'pool': pool_key, 'secs': secs,
                'time': _fmt_secs(secs), 'days_ago': (now - s.logged_at).days,
            }

    # --- check-ins: last 14 days vs the 14 before (fatigue/recovery signal) ---
    def _checkin_window(start, end):
        rows = (
            db.session.query(CheckIn)
            .filter(CheckIn.user_id == user_id, CheckIn.checkin_date >= start, CheckIn.checkin_date < end)
            .all()
        )
        def avg(vals):
            vals = [v for v in vals if v]
            return round(sum(vals) / len(vals), 2) if vals else None
        return {
            'feeling': avg([c.feeling_rating for c in rows]),
            'fatigue': avg([c.fatigue_rating for c in rows]),
            'sleep': avg([c.sleep_quality for c in rows]),
            'n': len(rows),
        }

    today = now.date()
    checkins_14d = _checkin_window(today - timedelta(days=14), today + timedelta(days=1))
    checkins_prev14 = _checkin_window(today - timedelta(days=28), today - timedelta(days=14))

    # --- squad attendance (if coached) ---
    att = (
        db.session.query(AttendanceRecord)
        .filter(AttendanceRecord.swimmer_id == user_id,
                AttendanceRecord.session_date >= today - timedelta(days=60))
        .all()
    )
    attendance = {'present': sum(1 for a in att if a.status in ('present', 'late')), 'total': len(att)}

    all_dates = sorted({s.logged_at.date() for s in swims} | {s.logged_at.date() for s in sessions})
    last_active = all_dates[-1].isoformat() if all_dates else None

    state = {
        'weekly': weekly,
        'acute_load': acute,
        'chronic_weekly_load': int(chronic_weekly),
        'acwr': acwr,
        'events': events,
        'pbs': pbs,
        'checkins_14d': checkins_14d,
        'checkins_prev14': checkins_prev14,
        'attendance_60d': attendance,
        'last_active': last_active,
        'total_logs': len(swims) + len(sessions),
    }
    trend, reason = classify_trend(state)
    state['trend'] = trend
    state['trend_reason'] = reason
    return state


def classify_trend(state, planned_days_per_week=None):
    """Classify the swimmer into one of swim_logic.TRENDS with a reason.
    Priority: physical-risk states (overtraining) first, then performance."""
    acwr = state.get('acwr')
    fatigue = (state.get('checkins_14d') or {}).get('fatigue')
    feeling = (state.get('checkins_14d') or {}).get('feeling')
    events = state.get('events') or {}

    improving = [e for e, d in events.items() if d['direction'] == 'improving']
    slipping = [e for e, d in events.items() if d['direction'] == 'slipping']

    # Overtraining: load spiking well above the body's recent normal, or a
    # milder spike combined with the swimmer telling us they're wrecked.
    if acwr is not None and acwr >= 1.7:
        return 'overtraining', (
            f'Training load this week is {acwr}x your recent 4-week normal, that ramp is faster than the body adapts.'
        )
    if acwr is not None and acwr >= 1.35 and ((fatigue and fatigue >= 3.5) or (feeling and feeling <= 2.2)):
        return 'overtraining', (
            f'Load is up ({acwr}x your recent normal) and your check-ins show high fatigue, classic early overtraining picture.'
        )

    # Undertraining: load well below the swimmer's own established normal.
    if acwr is not None and acwr <= 0.55 and state.get('chronic_weekly_load', 0) > 500:
        return 'undertraining', 'This week\'s volume is under 60% of your recent normal.'

    if improving and len(improving) > len(slipping):
        return 'improving', f"Times trending down in {', '.join(improving[:3])}."
    if slipping and len(slipping) > len(improving):
        return 'regressing', f"Times trending up in {', '.join(slipping[:3])}."
    if events:
        return 'plateauing', 'Times are holding steady rather than dropping.'
    return 'plateauing', 'Not enough repeated timed swims yet to read a performance trend.'


def update_athlete_state(user_id):
    """Recompute and persist the athlete state. Called after every logged
    swim/session/check-in -- wrapped so a failure here can never break the
    log itself."""
    try:
        from app import db
        from models import AthleteState

        state = recompute_state(user_id)
        row = db.session.query(AthleteState).filter_by(user_id=user_id).first()
        if not row:
            row = AthleteState(user_id=user_id)
            db.session.add(row)
        row.state_json = json.dumps(state)
        row.updated_at = datetime.utcnow()
        db.session.commit()
        return state
    except Exception:
        logger.exception('update_athlete_state failed for user %s', user_id)
        try:
            from app import db
            db.session.rollback()
        except Exception:
            pass
        return None


def get_state(user_id, max_age_hours=24):
    """Return a reasonably fresh athlete state, recomputing if stale/missing."""
    from app import db
    from models import AthleteState

    row = db.session.query(AthleteState).filter_by(user_id=user_id).first()
    if row and row.state_json and row.updated_at and \
            datetime.utcnow() - row.updated_at < timedelta(hours=max_age_hours):
        return row.get_state()
    return update_athlete_state(user_id) or (row.get_state() if row else {})


def get_states_batch(user_ids, max_age_hours=24):
    """Batch form of get_state() -- one query for every cached row instead of
    one query per user_id, so rendering a whole squad doesn't call get_state()
    once per SquadMembership (an N+1, and a double read for any swimmer who
    belongs to more than one squad under the same coach). Rows that are
    missing or stale still cost one recompute each, same as get_state() alone
    -- that work is unavoidable, this only removes the redundant cache reads.
    Returns {user_id: state_dict}."""
    from app import db
    from models import AthleteState

    unique_ids = {uid for uid in user_ids if uid}
    if not unique_ids:
        return {}

    rows_by_user = {
        r.user_id: r for r in
        db.session.query(AthleteState).filter(AthleteState.user_id.in_(unique_ids)).all()
    }
    now = datetime.utcnow()
    states = {}
    for uid in unique_ids:
        row = rows_by_user.get(uid)
        if row and row.state_json and row.updated_at and now - row.updated_at < timedelta(hours=max_age_hours):
            states[uid] = row.get_state()
        else:
            states[uid] = update_athlete_state(uid) or (row.get_state() if row else {})
    return states


# ---------------------------------------------------------------------------
# Weekly progress review (PART 2)
# ---------------------------------------------------------------------------

def ensure_weekly_report(user_id, api_key=None, model=None, tone='encouraging'):
    """Return the swimmer's current weekly report, generating a fresh one when
    the last is 7+ days old. Returns the report dict or None when there's not
    enough data to review. Never raises."""
    try:
        from app import db
        from models import WeeklyReport

        latest = (
            db.session.query(WeeklyReport)
            .filter_by(user_id=user_id)
            .order_by(WeeklyReport.created_at.desc())
            .first()
        )
        if latest and datetime.utcnow() - latest.created_at < timedelta(days=7):
            return latest.get_report()

        report = build_weekly_report(user_id, api_key=api_key, model=model, tone=tone)
        if report is None:
            return latest.get_report() if latest else None

        row = WeeklyReport(
            user_id=user_id,
            week_start=(datetime.utcnow() - timedelta(days=7)).date(),
            report_json=json.dumps(report),
        )
        db.session.add(row)

        # A generated review closes a training week: advance the progression
        # cycle counter that schedules recovery weeks.
        from models import AthleteState
        st = db.session.query(AthleteState).filter_by(user_id=user_id).first()
        if not st:
            st = AthleteState(user_id=user_id)
            db.session.add(st)
        st.week_index = (st.week_index or 0) + 1
        db.session.commit()
        return report
    except Exception:
        logger.exception('ensure_weekly_report failed for user %s', user_id)
        try:
            from app import db
            db.session.rollback()
        except Exception:
            pass
        return None


def build_weekly_report(user_id, api_key=None, model=None, tone='encouraging'):
    """The automatic 7-day review: current week vs previous weeks. Returns the
    report dict, or None when the swimmer has no recent data worth reviewing."""
    from app import db
    from models import Swim, Session, CheckIn, AthleteProfile

    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)

    swims = db.session.query(Swim).filter_by(user_id=user_id).order_by(Swim.logged_at.asc()).all()
    sessions = db.session.query(Session).filter_by(user_id=user_id).all()
    profile = db.session.query(AthleteProfile).filter_by(user_id=user_id).first()

    this_week_sessions = [s for s in sessions if s.logged_at >= week_ago]
    prev_week_sessions = [s for s in sessions if two_weeks_ago <= s.logged_at < week_ago]
    this_week_swims = [s for s in swims if s.logged_at >= week_ago]
    prev_week_swims = [s for s in swims if two_weeks_ago <= s.logged_at < week_ago]

    vol_this = sum(s.total_distance() for s in this_week_sessions) + sum(s.distance() for s in this_week_swims)
    vol_prev = sum(s.total_distance() for s in prev_week_sessions) + sum(s.distance() for s in prev_week_swims)
    n_this = len(this_week_sessions) + len(this_week_swims)
    n_prev = len(prev_week_sessions) + len(prev_week_swims)

    if not swims and not sessions:
        return None
    if n_this == 0 and n_prev == 0:
        return None  # nothing trained in a fortnight: no review to write

    state = get_state(user_id)

    # --- PBs improved this week: compare each new best against the previous
    # best in that event before this week ---
    pb_improvements = []
    for event in {s.event for s in this_week_swims}:
        older = [s.time_in_seconds() for s in swims
                 if s.event == event and s.logged_at < week_ago and s.time_in_seconds() is not None]
        this_wk = [s.time_in_seconds() for s in this_week_swims
                   if s.event == event and s.time_in_seconds() is not None]
        if not this_wk:
            continue
        new_best = min(this_wk)
        if older and new_best < min(older):
            pb_improvements.append({
                'event': event,
                'old': _fmt_secs(min(older)),
                'new': _fmt_secs(new_best),
                'gain': round(min(older) - new_best, 2),
            })

    # --- consistency vs their own plan ---
    planned = (profile.training_days_per_week if profile and profile.training_days_per_week else None)
    if planned:
        consistency_pct = min(100, round(n_this / planned * 100))
    else:
        consistency_pct = min(100, round(n_this / max(1, n_prev or n_this) * 100))
    missed = max(0, (planned or 0) - n_this) if planned else None

    # --- recovery read from check-ins this week ---
    week_checkins = (
        db.session.query(CheckIn)
        .filter(CheckIn.user_id == user_id, CheckIn.checkin_date >= week_ago.date())
        .all()
    )
    fatigues = [c.fatigue_rating for c in week_checkins if c.fatigue_rating]
    sleeps = [c.sleep_quality for c in week_checkins if c.sleep_quality]
    avg_fatigue = sum(fatigues) / len(fatigues) if fatigues else None
    avg_sleep = sum(sleeps) / len(sleeps) if sleeps else None
    if avg_fatigue is not None and avg_fatigue >= 3.5:
        recovery_status = 'run down'
    elif (avg_fatigue is not None and avg_fatigue <= 2.2) and (avg_sleep is None or avg_sleep >= 3.5):
        recovery_status = 'fresh'
    elif avg_fatigue is None and not week_checkins:
        recovery_status = 'unknown'
    else:
        recovery_status = 'normal'

    # --- progress score, 0-100: an honest blend, not a vanity number ---
    score = 50.0
    events = state.get('events') or {}
    if events:
        avg_change = sum(-d['change_pct'] for d in events.values()) / len(events)  # + = faster
        score += max(-20, min(20, avg_change * 8))
    if vol_prev > 0:
        score += max(-10, min(10, (vol_this - vol_prev) / vol_prev * 25))
    if planned:
        score += (consistency_pct - 70) * 0.15
    score += len(pb_improvements) * 5
    if recovery_status == 'run down':
        score -= 8
    trend = state.get('trend')
    if trend == 'overtraining':
        score -= 10
    progress_pct = int(max(5, min(98, round(score))))

    # --- strengths / weaknesses from the actual signals ---
    strengths, weaknesses = [], []
    for event, d in events.items():
        if d['direction'] == 'improving':
            strengths.append(f"{event} trending {abs(d['change_pct']):.1f}% faster")
        elif d['direction'] == 'slipping':
            weaknesses.append(f"{event} trending {abs(d['change_pct']):.1f}% slower")
    if pb_improvements:
        strengths.append(f"{len(pb_improvements)} new personal best{'s' if len(pb_improvements) != 1 else ''} this week")
    if planned and n_this >= planned:
        strengths.append('Hit every planned session this week')
    if missed:
        weaknesses.append(f"Missed {missed} planned session{'s' if missed != 1 else ''}")
    if recovery_status == 'run down':
        weaknesses.append('Check-ins show fatigue building')
    if recovery_status == 'fresh':
        strengths.append('Recovering well between sessions')
    if not strengths:
        strengths.append('Kept training ticking over' if n_this else 'History on the board to build from')
    if not weaknesses:
        weaknesses.append('Nothing flagged, keep doing what you\'re doing')

    # --- confidence: how much data this review actually stands on ---
    data_points = n_this + n_prev + len(week_checkins) + sum(d['n'] for d in events.values())
    confidence = 'high' if data_points >= 20 else 'medium' if data_points >= 8 else 'low'

    # --- next week, from the progression engine ---
    from models import AthleteState
    st_row = db.session.query(AthleteState).filter_by(user_id=user_id).first()
    week_index = (st_row.week_index or 0) if st_row else 0
    last_full_week_vol = vol_this if vol_this > 0 else vol_prev
    target = swim_logic.next_week_target(
        last_full_week_vol, week_index, trend,
        level=(profile.level if profile else None),
        days_per_week=(planned or 3),
    )

    focus_by_trend = {
        'improving': 'Keep the build going, and start sharpening: a touch more race-pace work.',
        'plateauing': 'Change the stimulus: new intervals and set structures this week rather than more metres.',
        'regressing': 'Pull volume back, prioritise sleep and technique, and rebuild from there.',
        'overtraining': 'Back off deliberately this week. Recovery is the training.',
        'undertraining': 'Rebuild the routine: consistency beats any single big session.',
    }
    suggested_focus = focus_by_trend.get(trend, 'Consistent aerobic work with one quality session.')
    if target['kind'] == 'recovery':
        suggested_focus = 'Scheduled recovery week: easy aerobic swimming and technique, volume down on purpose.'
    elif target['kind'] == 'baseline':
        suggested_focus = 'Get back to a steady rhythm first: showing up beats any single big session right now.'

    report = {
        'generated_at': now.isoformat(),
        'window': {'from': week_ago.date().isoformat(), 'to': now.date().isoformat()},
        'progress_pct': progress_pct,
        'trend': trend,
        'trend_reason': state.get('trend_reason', ''),
        'volume': {'this_week': vol_this, 'prev_week': vol_prev},
        'sessions': {'this_week': n_this, 'prev_week': n_prev, 'planned': planned},
        'pb_improvements': pb_improvements,
        'strengths': strengths[:4],
        'weaknesses': weaknesses[:4],
        'consistency_pct': consistency_pct,
        'recovery_status': recovery_status,
        'confidence': confidence,
        'suggested_focus': suggested_focus,
        'next_week': target,
    }

    # --- optional AI narrative on top of the deterministic review ---
    if api_key and model:
        try:
            from ai_utils import generate_weekly_review
            digest = _report_digest_text(report)
            ai = generate_weekly_review(digest, api_key, model, tone=tone)
            if ai.get('ok'):
                report['ai_review'] = ai['review']
        except Exception:
            logger.exception('weekly report AI narrative failed (report still saved)')

    return report


def _report_digest_text(report):
    v, s = report['volume'], report['sessions']
    lines = [
        f"Trend: {report['trend']} ({report['trend_reason']})",
        f"Volume: {v['this_week']}m this week vs {v['prev_week']}m last week",
        f"Sessions: {s['this_week']} this week vs {s['prev_week']} last week"
        + (f" (planned {s['planned']}/week)" if s['planned'] else ''),
        f"Consistency: {report['consistency_pct']}%",
        f"Recovery: {report['recovery_status']}",
        f"Progress score: {report['progress_pct']}/100 (confidence {report['confidence']})",
    ]
    if report['pb_improvements']:
        lines.append('New PBs: ' + ', '.join(
            f"{p['event']} {p['old']} -> {p['new']}" for p in report['pb_improvements']))
    lines.append('Strengths: ' + '; '.join(report['strengths']))
    lines.append('Weaknesses: ' + '; '.join(report['weaknesses']))
    lines.append(f"Next week plan: {report['next_week']['kind']} week, about {report['next_week']['volume']}m. "
                 f"{report['next_week']['why']}")
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Adaptive program context (PART 3 + PART 7)
# ---------------------------------------------------------------------------

def adaptation_context(user_id, profile):
    """Build the adaptive-coaching block injected into the program-builder
    prompt, plus the machine-readable target. Returns (text, target) --
    (None, None) when the swimmer has no history yet (first program)."""
    try:
        from app import db
        from models import AthleteState

        state = get_state(user_id)
        if not state or state.get('total_logs', 0) < 3:
            return None, None

        weekly = state.get('weekly') or []
        completed = [w['vol'] for w in weekly[:-1] if w['vol'] > 0]
        last_vol = completed[-1] if completed else 0
        st_row = db.session.query(AthleteState).filter_by(user_id=user_id).first()
        week_index = (st_row.week_index or 0) if st_row else 0

        target = swim_logic.next_week_target(
            last_vol, week_index, state.get('trend'),
            level=profile.level, days_per_week=profile.training_days_per_week or 3,
        )

        kind_instructions = {
            'baseline': 'Build a sensible starting week for their level.',
            'build': ('They earned a progression: increase total volume toward the target, tighten one or two '
                      'send-off intervals slightly vs a standard week, and include some race-pace work.'),
            'recovery': ('This is a RECOVERY WEEK: keep everything aerobic and technical, generous intervals, '
                         'no lactate or max-effort work, volume down around the target.'),
            'stimulus-change': ('They have plateaued: keep volume similar but CHANGE THE STIMULUS -- different '
                                'set structures, different intervals, a new emphasis (e.g. swap threshold work '
                                'for sprint or technique blocks) so training feels new.'),
            'reduce': ('They are fatigued/regressing: reduce volume to the target, lengthen rest and intervals, '
                       'simplify the sets, and bias toward technique and easy aerobic swimming.'),
            'rebuild': 'They have been undertraining: rebuild volume gently toward the target with achievable sessions.',
            'steady': 'Continue the current approach with a small nudge forward.',
        }

        events = state.get('events') or {}
        event_lines = [
            f"  - {ev}: {d['direction']} ({d['change_pct']:+.1f}%), recent avg {_fmt_secs(d['recent_avg'])} over {d['n']} swims"
            for ev, d in list(events.items())[:5]
        ]
        ck = state.get('checkins_14d') or {}
        ck_line = None
        if ck.get('n'):
            bits = [f"{k} {v}/5" for k, v in (('feeling', ck.get('feeling')), ('fatigue', ck.get('fatigue')),
                                              ('sleep', ck.get('sleep'))) if v]
            ck_line = f"Recent check-ins (14d, n={ck['n']}): " + ', '.join(bits)

        text_lines = [
            "ADAPTIVE COACHING CONTEXT (built from this swimmer's actual training history -- use it):",
            f"- Current trend: {state.get('trend')} -- {state.get('trend_reason')}",
            f"- Last completed week: {last_vol}m"
            + (f"; recent weeks: {', '.join(str(v) for v in completed[-4:])}m" if completed else ''),
        ]
        if event_lines:
            text_lines.append('- Event time trends:\n' + '\n'.join(event_lines))
        if ck_line:
            text_lines.append(f'- {ck_line}')
        text_lines.append(
            f"- NEXT WEEK TARGET: about {target['volume']}m total ({target['kind']} week). {target['why']}"
        )
        text_lines.append(f"- Adjustment: {kind_instructions.get(target['kind'], '')}")
        text_lines.append(
            "- Fill the 'adaptation_note' field with 1-2 sentences telling the swimmer plainly what changed "
            "in this week's plan vs their recent training and WHY (grounded in the data above)."
        )
        return '\n'.join(text_lines), target
    except Exception:
        logger.exception('adaptation_context failed for user %s', user_id)
        return None, None


# ---------------------------------------------------------------------------
# Check-in cadence (PART 4): nudge every 3-4 days, short and natural
# ---------------------------------------------------------------------------

CHECKIN_QUESTIONS = [
    "How did your last few sessions feel?",
    "Any shoulder soreness or niggles I should know about?",
    "Did your usual pace feel any easier this week?",
    "How's your energy been this week?",
    "Have you missed any sessions lately? No judgement, it just helps me plan.",
    "How motivated are you feeling right now?",
]

CHECKIN_INTERVAL_DAYS = 3


def checkin_nudge(user_id):
    """Return {'due', 'question', 'days_since'} for the gentle every-3-4-days
    check-in prompt. The question rotates deterministically so it doesn't
    change on every page load."""
    try:
        from app import db
        from models import CheckIn

        today = datetime.utcnow().date()
        last = (
            db.session.query(CheckIn)
            .filter_by(user_id=user_id)
            .order_by(CheckIn.checkin_date.desc())
            .first()
        )
        days_since = (today - last.checkin_date).days if last else None
        due = last is None or days_since >= CHECKIN_INTERVAL_DAYS
        question = CHECKIN_QUESTIONS[(today.toordinal() // CHECKIN_INTERVAL_DAYS) % len(CHECKIN_QUESTIONS)]
        return {'due': due, 'question': question, 'days_since': days_since}
    except Exception:
        logger.exception('checkin_nudge failed for user %s', user_id)
        return {'due': False, 'question': CHECKIN_QUESTIONS[0], 'days_since': None}
