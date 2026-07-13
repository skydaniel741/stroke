from datetime import datetime, timedelta

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, jsonify, current_app
from flask_login import login_required, current_user

from auth_utils import solo_required

solo = Blueprint('solo', __name__, url_prefix='/solo')

MAX_SCAN_BYTES = 20 * 1024 * 1024  # raw phone-camera uploads before we downscale server-side
WEEKLY_REGEN_LIMIT = 3  # AI program rebuilds allowed per rolling week


@solo.route('/locked')
@login_required
def locked():
    # NOT solo_required -- this IS where solo_required sends people, a
    # redirect loop otherwise. Reachable by anyone signed in: free-plan users
    # and solo/solo_pro users who haven't been marked paid yet both land here.
    return render_template('solo_locked.html')


@solo.route('/scan-whiteboard', methods=['POST'])
@login_required
@solo_required
def scan_whiteboard():
    if not current_app.config.get('AI_SCAN_ENABLED'):
        return jsonify({'ok': False, 'error': "Photo scan isn't set up yet."}), 503

    file = request.files.get('photo')
    if not file or not file.filename:
        return jsonify({'ok': False, 'error': 'Choose a photo first.'}), 400

    image_bytes = file.read()
    if len(image_bytes) > MAX_SCAN_BYTES:
        return jsonify({'ok': False, 'error': 'That photo is too large — try a smaller image.'}), 400

    # No content-type allowlist here on purpose -- phones report HEIC/HEIF for
    # gallery photos and browsers aren't always consistent about mimetypes.
    # ai_utils.normalize_image() opens whatever we're given and rejects
    # anything that isn't actually a readable image.
    from ai_utils import extract_set_from_image
    result = extract_set_from_image(
        image_bytes,
        current_app.config['ANTHROPIC_API_KEY'],
        current_app.config['ANTHROPIC_MODEL'],
    )
    return jsonify(result), (200 if result.get('ok') else 422)


@solo.route('/parse-transcript', methods=['POST'])
@login_required
@solo_required
def parse_transcript():
    if not current_app.config.get('AI_SCAN_ENABLED'):
        return jsonify({'ok': False, 'error': "Voice log isn't set up yet."}), 503

    transcript = (request.form.get('transcript') or '').strip()
    if not transcript:
        return jsonify({'ok': False, 'error': "Didn't catch anything — try dictating again."}), 400

    from ai_utils import extract_set_from_transcript
    result = extract_set_from_transcript(
        transcript,
        current_app.config['ANTHROPIC_API_KEY'],
        current_app.config['ANTHROPIC_MODEL'],
    )
    return jsonify(result), (200 if result.get('ok') else 422)


@solo.route('/onboarding', methods=['GET', 'POST'])
@login_required
@solo_required
def onboarding():
    from app import db
    from models import AthleteProfile, TrainingProgram

    existing = db.session.query(AthleteProfile).filter_by(user_id=current_user.id).first()

    if request.method == 'POST':
        if not current_app.config.get('ANTHROPIC_API_KEY'):
            flash("AI program generation isn't set up yet.", 'error')
            return redirect(url_for('solo.onboarding'))

        # Rebuilds are capped at WEEKLY_REGEN_LIMIT per rolling week (Mon-Sun).
        # The very first build (no program yet) is always free.
        is_rebuild = bool(existing and existing.program_json)
        monday = datetime.utcnow().date() - timedelta(days=datetime.utcnow().weekday())
        week_used = (existing.regen_count or 0) if (existing and existing.regen_week_start == monday) else 0
        if is_rebuild and week_used >= WEEKLY_REGEN_LIMIT:
            reset = monday + timedelta(days=7)
            flash(
                f"You've used all {WEEKLY_REGEN_LIMIT} program rebuilds this week. "
                f"You can rebuild again on {reset.strftime('%a %d %b')}.",
                'error',
            )
            return redirect(url_for('solo.program'))

        from validation import clean_int, clean_text

        age_raw = (request.form.get('age') or '').strip()
        age = clean_int(age_raw, key='age')
        if age_raw and age is None:
            flash('Age needs to be a whole number between 5 and 99.', 'error')
            return redirect(url_for('solo.onboarding'))

        days_raw = (request.form.get('training_days_per_week') or '').strip()
        training_days = clean_int(days_raw, key='training_days', hi=7)
        if days_raw and training_days is None:
            flash('Training days per week needs to be a whole number from 1 to 7.', 'error')
            return redirect(url_for('solo.onboarding'))

        profile = existing or AthleteProfile(user_id=current_user.id)
        profile.level = clean_text(request.form.get('level'), 30)
        profile.age = age
        profile.training_days_per_week = training_days
        profile.fitness_ability = clean_text(request.form.get('fitness_ability'), 30)
        profile.primary_stroke = clean_text(request.form.get('primary_stroke'), 20)
        profile.main_goal = clean_text(request.form.get('main_goal'), 1000)
        profile.swimmer_type = clean_text(request.form.get('swimmer_type'), 30)
        coaching_situation = request.form.get('coaching_situation', 'none')
        profile.coaching_situation = coaching_situation if coaching_situation in (
            'none', 'club_want_extra', 'club_want_structure', 'self_coached'
        ) else 'none'
        profile.coaching_focus = (
            (clean_text(request.form.get('coaching_focus'), 500) or None) if profile.coaching_situation != 'none' else None
        )
        eating_habits = request.form.get('eating_habits', 'balanced')
        profile.eating_habits = eating_habits if eating_habits in (
            'undereating', 'balanced', 'skip_meals', 'structured'
        ) else 'balanced'
        profile.limitations = clean_text(request.form.get('limitations'), 500) or None

        # AI tuning is available to every solo swimmer (Solo Pro was removed).
        tone = request.form.get('coaching_tone', 'balanced')
        profile.coaching_tone = tone if tone in ('encouraging', 'balanced', 'direct') else 'balanced'
        intensity = request.form.get('intensity', 'normal')
        profile.intensity = intensity if intensity in ('easier', 'normal', 'harder') else 'normal'

        profile.updated_at = datetime.utcnow()

        # Real, existing catalogs the AI curates from -- it never invents new
        # meals, supplements or dryland programs, it only picks IDs out of these.
        from nutrition_data import MEALS, PRODUCTS
        meal_catalog = [{'id': m['id'], 'name': m['name'], 'category': m['category']} for m in MEALS]
        supplement_catalog = [
            {'id': p['id'], 'name': p['name'], 'category': p['category'], 'evidence': p.get('evidence', '')}
            for p in PRODUCTS
        ]
        dryland_rows = (
            db.session.query(TrainingProgram)
            .filter(TrainingProgram.category != 'Nutrition')
            .all()
        )
        dryland_catalog = [{'id': p.id, 'title': p.title, 'category': p.category} for p in dryland_rows]

        # Adaptive coaching: rebuilds get the swimmer's real history (trend,
        # load, fatigue, next-week target from the progression engine) so the
        # program evolves instead of resetting to a generic week each time.
        import athlete_model
        adaptation_text, _target = athlete_model.adaptation_context(current_user.id, profile)

        from ai_utils import generate_training_program
        result = generate_training_program(
            profile, meal_catalog, dryland_catalog, supplement_catalog,
            current_app.config['ANTHROPIC_API_KEY'],
            current_app.config['ANTHROPIC_MODEL'],
            adaptation=adaptation_text,
        )
        if not result.get('ok'):
            flash(result.get('error', "Couldn't generate a program — try again."), 'error')
            return redirect(url_for('solo.onboarding'))

        # Realism pass: every block is checked against what this swimmer can
        # actually swim (send-off vs swim time vs rest). Impossible intervals
        # get fixed deterministically; oversized days get trimmed.
        import swim_logic
        fixes = swim_logic.validate_program(
            result['program'], level=profile.level, age=profile.age, fitness=profile.fitness_ability,
        )
        if fixes:
            result['program']['realism_fixes'] = fixes[:8]

        import json
        profile.program_json = json.dumps(result['program'])
        profile.nutrition_json = json.dumps(result['nutrition'])
        profile.dryland_json = json.dumps(result['dryland'])
        # Count this against the weekly rebuild cap (only rebuilds, not the
        # first-ever build).
        if is_rebuild:
            profile.regen_week_start = monday
            profile.regen_count = week_used + 1
        if not existing:
            db.session.add(profile)
        db.session.commit()
        flash('Your personalized program is ready.', 'success')
        return redirect(url_for('solo.program'))

    regens_left = existing.regens_left(WEEKLY_REGEN_LIMIT) if existing else WEEKLY_REGEN_LIMIT
    return render_template(
        'solo_onboarding.html', profile=existing,
        regens_left=regens_left, regen_limit=WEEKLY_REGEN_LIMIT,
        is_rebuild=bool(existing and existing.program_json),
    )


@solo.route('/program')
@login_required
@solo_required
def program():
    from app import db
    from models import AthleteProfile, TrainingProgram
    from nutrition_data import meal_by_id, product_by_id
    from demo_library import demos_for_stroke, demos_for_dryland_category

    profile = db.session.query(AthleteProfile).filter_by(user_id=current_user.id).first()
    if not profile or not profile.program_json:
        return redirect(url_for('solo.onboarding'))

    nutrition = profile.get_nutrition()
    nutrition_meals = [
        m for m in (meal_by_id(mid) for mid in nutrition.get('recommended_meal_ids', [])) if m
    ]
    nutrition_supplements = [
        p for p in (product_by_id(sid) for sid in nutrition.get('recommended_supplement_ids', [])) if p
    ]

    dryland = profile.get_dryland()
    dryland_ids = dryland.get('recommended_program_ids', [])
    dryland_rows = (
        db.session.query(TrainingProgram).filter(TrainingProgram.id.in_(dryland_ids)).all()
        if dryland_ids else []
    )
    dryland_by_id = {p.id: p for p in dryland_rows}
    dryland_programs = [dryland_by_id[pid] for pid in dryland_ids if pid in dryland_by_id]

    stroke_demos = demos_for_stroke(profile.primary_stroke)
    dryland_demo_slugs_seen = set()
    dryland_demos = []
    for p in dryland_programs:
        for d in demos_for_dryland_category(p.category):
            if d['slug'] not in dryland_demo_slugs_seen:
                dryland_demo_slugs_seen.add(d['slug'])
                dryland_demos.append(d)

    # Calendar: the AI schema guarantees program.days is exactly 7 entries,
    # Monday-Sunday in order, so it maps 1:1 onto this week's real dates.
    # "Next week" only shows the date strip (no content) -- the AI builds
    # one week at a time, filled in by the next rebuild.
    def _fmt(d):
        return f"{d.day} {d.strftime('%b')}"  # avoid %-d/%#d: not portable across platforms

    program = profile.get_program()
    today = datetime.utcnow().date()
    week_start = today - timedelta(days=today.weekday())
    week_dates = [week_start + timedelta(days=i) for i in range(7)]
    next_week_dates = [week_start + timedelta(days=7 + i) for i in range(7)]
    calendar_days = list(zip(program.get('days') or [], week_dates)) if program.get('days') else []
    week_range = f"{_fmt(week_dates[0])} – {_fmt(week_dates[-1])}"
    next_week_range = f"{_fmt(next_week_dates[0])} – {_fmt(next_week_dates[-1])}"

    return render_template(
        'solo_program.html', profile=profile, program=program,
        calendar_days=calendar_days, next_week_dates=next_week_dates, today=today,
        week_range=week_range, next_week_range=next_week_range,
        nutrition=nutrition, nutrition_meals=nutrition_meals,
        nutrition_supplements=nutrition_supplements,
        dryland=dryland, dryland_programs=dryland_programs,
        stroke_demos=stroke_demos, dryland_demos=dryland_demos,
        regens_left=profile.regens_left(WEEKLY_REGEN_LIMIT), regen_limit=WEEKLY_REGEN_LIMIT,
    )


@solo.route('/pro')
@login_required
@solo_required
def pro():
    return render_template('solo_pro.html')


@solo.route('/pro/upgrade', methods=['POST'])
@login_required
@solo_required
def pro_upgrade():
    from app import db

    # Placeholder for real checkout. In production this is where a Stripe
    # (or similar) payment would be confirmed before flipping the plan.
    current_user.plan = 'solo_pro'
    db.session.commit()
    flash('Welcome to Solo Pro — AI tuning is unlocked.', 'success')
    return redirect(url_for('solo.onboarding'))


@solo.route('/pro/downgrade', methods=['POST'])
@login_required
@solo_required
def pro_downgrade():
    from app import db

    current_user.plan = 'solo'
    db.session.commit()
    flash('Back on the free Solo plan.', 'success')
    return redirect(url_for('solo.pro'))


@solo.route('/checkin', methods=['GET', 'POST'])
@login_required
@solo_required
def checkin():
    from app import db
    from models import AthleteProfile, CheckIn

    profile = db.session.query(AthleteProfile).filter_by(user_id=current_user.id).first()
    today = datetime.utcnow().date()

    if request.method == 'POST':
        if not profile:
            flash('Set up your training program first.', 'error')
            return redirect(url_for('solo.onboarding'))

        from validation import clean_int, clean_text
        feeling = clean_int(request.form.get('feeling_rating'), key='rating') or 0
        # Free text: cap length and mask profanity before it ever hits the DB
        # or the AI prompt (a pasted file / a slur can't get through).
        notes = clean_text(request.form.get('notes'), 2000)
        if feeling < 1 or feeling > 5:
            flash('Rate how you felt from 1 to 5.', 'error')
            return redirect(url_for('solo.checkin'))

        def _optional_rating(field):
            try:
                v = int(request.form.get(field) or 0)
            except ValueError:
                v = 0
            return v if 1 <= v <= 5 else None

        fatigue = _optional_rating('fatigue_rating')
        sleep = _optional_rating('sleep_quality')

        recent = (
            db.session.query(CheckIn)
            .filter_by(user_id=current_user.id)
            .order_by(CheckIn.checkin_date.desc())
            .limit(7)
            .all()
        )
        recent_for_ai = [
            {
                'date': c.checkin_date.isoformat(), 'feeling_rating': c.feeling_rating,
                'fatigue_rating': c.fatigue_rating, 'sleep_quality': c.sleep_quality, 'notes': c.notes or '',
            }
            for c in reversed(recent)
        ]

        from ai_utils import generate_checkin_insight
        insight = generate_checkin_insight(
            profile, feeling, notes, recent_for_ai,
            current_app.config['ANTHROPIC_API_KEY'],
            current_app.config['ANTHROPIC_MODEL'],
            fatigue_rating=fatigue, sleep_quality=sleep,
        )

        existing_today = (
            db.session.query(CheckIn)
            .filter_by(user_id=current_user.id, checkin_date=today)
            .first()
        )
        entry = existing_today or CheckIn(user_id=current_user.id, checkin_date=today)
        entry.feeling_rating = feeling
        entry.fatigue_rating = fatigue
        entry.sleep_quality = sleep
        entry.notes = notes
        entry.ai_insight = insight
        if not existing_today:
            db.session.add(entry)
        db.session.commit()

        # Every check-in feeds the persisted athlete model (fatigue/recovery
        # signals shape the next adaptive program and weekly review).
        import athlete_model
        athlete_model.update_athlete_state(current_user.id)

        flash('Check-in saved.', 'success')
        return redirect(url_for('solo.checkin'))

    todays_checkin = (
        db.session.query(CheckIn)
        .filter_by(user_id=current_user.id, checkin_date=today)
        .first()
    )
    history = (
        db.session.query(CheckIn)
        .filter_by(user_id=current_user.id)
        .order_by(CheckIn.checkin_date.desc())
        .limit(14)
        .all()
    )

    import athlete_model
    nudge = athlete_model.checkin_nudge(current_user.id)

    return render_template(
        'solo_checkin.html',
        profile=profile,
        todays_checkin=todays_checkin,
        history=history,
        coach_question=nudge['question'],
    )


# ---------------------------------------------------------------------------
# Deep performance analytics. All of this is plain, deterministic math on the
# swimmer's own logged data (times + 50m splits) -- no AI, so it's always
# correct and cheap. The AI progress insight (routes.personal_bests) sits on
# top of numbers like these.
# ---------------------------------------------------------------------------

# Chart geometry: a plot area inside gutters that leave room for axis labels.
_CHART_W, _CHART_H = 320, 118
_PLOT_X0, _PLOT_X1 = 38, 312     # left gutter holds the y-axis time labels
_PLOT_Y0, _PLOT_Y1 = 10, 92      # bottom gutter holds the x-axis date labels

# Distinct line colours for the multi-event comparison chart.
_SERIES_COLORS = ['#5474d4', '#e07a5f', '#2a9d8f', '#e9a020', '#9b5de5', '#e0518b']


def _smooth_path(points):
    """Catmull-Rom -> cubic-bezier so the progression line is a smooth curve
    through every point (like a race-time graph), not a jagged polyline."""
    if not points:
        return ''
    if len(points) < 3:
        return 'M ' + ' L '.join(f"{p['x']},{p['y']}" for p in points)
    n = len(points)
    d = f"M {points[0]['x']},{points[0]['y']}"
    for i in range(n - 1):
        p0 = points[i - 1] if i > 0 else points[0]
        p1, p2 = points[i], points[i + 1]
        p3 = points[i + 2] if i + 2 < n else points[i + 1]
        cp1x = p1['x'] + (p2['x'] - p0['x']) / 6
        cp1y = p1['y'] + (p2['y'] - p0['y']) / 6
        cp2x = p2['x'] - (p3['x'] - p1['x']) / 6
        cp2y = p2['y'] - (p3['y'] - p1['y']) / 6
        d += f" C {cp1x:.1f},{cp1y:.1f} {cp2x:.1f},{cp2y:.1f} {p2['x']},{p2['y']}"
    return d


def _an_parse_secs(t):
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


def _an_fmt(secs):
    if secs is None:
        return '—'
    if secs >= 60:
        return f'{int(secs // 60)}:{secs % 60:05.2f}'
    return f'{secs:.2f}'


def _event_distance(event):
    import re
    m = re.match(r'\s*(\d+)', event or '')
    return int(m.group(1)) if m else 0


def _build_analytics(user_id):
    """Return everything the analytics page renders: per-event progression
    line charts, weekly volume bars, per-swim split (pacing) analysis, and
    even-split pace targets from the swimmer's goals."""
    from app import db
    from models import Swim, Session, Goal

    swims = db.session.query(Swim).filter_by(user_id=user_id).order_by(Swim.logged_at.desc()).all()
    sessions = db.session.query(Session).filter_by(user_id=user_id).all()

    # --- progression line charts (up to 4 most-logged events) ---
    by_event = {}
    for s in swims:
        secs = s.time_in_seconds()
        if secs is not None:
            by_event.setdefault(s.event, []).append((s.logged_at, secs))

    plot_w = _PLOT_X1 - _PLOT_X0
    plot_h = _PLOT_Y1 - _PLOT_Y0

    def _x_at(i, n):
        return _PLOT_X0 + plot_w * (i / (n - 1) if n > 1 else 0.5)

    progression = []
    ranked_events = sorted(by_event.items(), key=lambda kv: len(kv[1]), reverse=True)
    for event, entries in ranked_events:
        if len(entries) < 3:
            continue
        pts = sorted(entries, key=lambda e: e[0])  # oldest -> newest
        times = [secs for _, secs in pts]
        t_min, t_max = min(times), max(times)
        span = (t_max - t_min) or 1.0
        n = len(pts)
        points = []
        for i, (dt, secs) in enumerate(pts):
            x = _x_at(i, n)
            frac = (secs - t_min) / span  # 0 = fastest -> top of chart
            y = _PLOT_Y0 + plot_h * frac
            points.append({'x': round(x, 1), 'y': round(y, 1), 'label': _an_fmt(secs), 'date': dt.strftime('%d %b')})
        # y-axis ticks: fastest at top, slowest at bottom, midpoint between.
        y_ticks = [
            {'y': _PLOT_Y0, 'label': _an_fmt(t_min)},
            {'y': (_PLOT_Y0 + _PLOT_Y1) / 2, 'label': _an_fmt((t_min + t_max) / 2)},
            {'y': _PLOT_Y1, 'label': _an_fmt(t_max)},
        ]
        # x-axis ticks: first, middle, last swim dates.
        x_ticks = [
            {'x': points[0]['x'], 'label': points[0]['date'], 'anchor': 'start'},
            {'x': points[n // 2]['x'], 'label': points[n // 2]['date'], 'anchor': 'middle'},
            {'x': points[-1]['x'], 'label': points[-1]['date'], 'anchor': 'end'},
        ]
        first, last = times[0], times[-1]
        change = (last - first) / first * 100 if first else 0
        trend = 'improving' if change < -0.4 else 'slipping' if change > 0.4 else 'steady'
        progression.append({
            'event': event,
            'points': points,
            'path': _smooth_path(points),
            'y_ticks': y_ticks,
            'x_ticks': x_ticks,
            'best': _an_fmt(t_min),
            'latest': _an_fmt(last),
            'trend': trend,
            'change_pct': round(abs(change), 1),
            'count': n,
        })
        if len(progression) >= 4:
            break

    # --- multi-event comparison: normalised % improvement per event on one
    # chart, so you can see which events you're improving fastest in (the
    # "sprint improving faster than 400" view). Higher on the chart = more
    # improvement from your starting point. ---
    comparison = None
    comp_series = []
    for idx, (event, entries) in enumerate(e for e in ranked_events if len(e[1]) >= 3):
        if idx >= 6:
            break
        pts = sorted(entries, key=lambda e: e[0])
        base = pts[0][1]
        if not base:
            continue
        improve = [(dt, (base - secs) / base * 100) for dt, secs in pts]  # +% = faster than start
        comp_series.append({'event': event, 'improve': improve, 'latest_pct': round(improve[-1][1], 1)})
    if len(comp_series) >= 2:
        all_vals = [v for s in comp_series for _, v in s['improve']]
        lo = min(all_vals + [0.0])
        hi = max(all_vals + [0.5])
        vspan = (hi - lo) or 1.0

        def _cy(v):
            return _PLOT_Y1 - (v - lo) / vspan * plot_h

        series_out = []
        for si, s in enumerate(comp_series):
            m = len(s['improve'])
            spts = [{'x': round(_x_at(i, m), 1), 'y': round(_cy(v), 1)} for i, (_, v) in enumerate(s['improve'])]
            series_out.append({
                'event': s['event'],
                'color': _SERIES_COLORS[si % len(_SERIES_COLORS)],
                'path': _smooth_path(spts),
                'end': spts[-1],
                'latest_pct': s['latest_pct'],
            })
        comparison = {
            'series': series_out,
            'zero_y': round(_cy(0), 1),
            'top_label': f"+{hi:.0f}%",
            'bottom_label': f"{lo:.0f}%",
        }

    # --- weekly volume bars (last 12 weeks) ---
    now = datetime.utcnow()
    week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    weeks = []
    for i in range(11, -1, -1):
        ws = week_start - timedelta(weeks=i)
        we = ws + timedelta(days=7)
        vol = (
            sum(s.total_distance() for s in sessions if ws <= s.logged_at < we)
            + sum(s.distance() for s in swims if ws <= s.logged_at < we)
        )
        weeks.append({'vol': vol, 'label': ws.strftime('%d %b')})
    max_vol = max((w['vol'] for w in weeks), default=0) or 1
    for w in weeks:
        w['h'] = round(w['vol'] / max_vol * 100)
    total_12wk = sum(w['vol'] for w in weeks)

    # --- split (pacing) analysis, from logged 50m splits ---
    split_analyses = []
    for s in swims:
        raw = s.get_splits()
        secs_list = [v for v in (_an_parse_secs(x) for x in raw) if v is not None]
        if len(secs_list) < 2:
            continue
        n = len(secs_list)
        max_s = max(secs_list)
        bars = [
            {'idx': i + 1, 'secs': v, 'label': _an_fmt(v), 'h': round(v / max_s * 100)}
            for i, v in enumerate(secs_list)
        ]
        half = n // 2
        first = secs_list[:half]
        second = secs_list[-half:]
        first_avg = sum(first) / len(first)
        second_avg = sum(second) / len(second)
        fade = (second_avg - first_avg) / first_avg * 100 if first_avg else 0
        # Reality check on pacing: the back half is almost always slower. The
        # first 50 carries the dive/push (roughly half a second of free speed)
        # and fatigue builds through the race, so a small positive split is the
        # NORMAL, well-paced outcome. A true negative split (faster back half)
        # is genuinely hard and a mark of excellent pacing and aerobic strength.
        # So we only flag a real problem when the drop-off is large.
        if fade <= -0.5:
            pattern = 'negative'
            note = ("Negative split, you actually came home faster. That's genuinely hard to do and a sign of "
                    "great pacing and aerobic strength. Most swimmers can't, so this is a real strength.")
        elif fade <= 3:
            pattern = 'even'
            note = ("Well paced. The back half being a touch slower is completely normal (your first 50 has the "
                    "dive), so this is strong, controlled pacing.")
        elif fade <= 7:
            pattern = 'normal-fade'
            note = ("A normal amount of fade for the distance, and some of it is just the dive advantage on your "
                    "first 50. Holding a little more through the back half is where your next bit of time is.")
        else:
            pattern = 'big-fade'
            note = ("Big drop-off in the back half. That usually means you went out too fast for your current "
                    "fitness. Try starting a touch more controlled, your back half will thank you.")
        split_analyses.append({
            'event': s.event,
            'date': s.logged_at.strftime('%d %b %Y'),
            'time': s.time,
            'bars': bars,
            'first_avg': _an_fmt(first_avg),
            'second_avg': _an_fmt(second_avg),
            'fade_pct': round(fade, 1),
            'pattern': pattern,
            'note': note,
        })
        if len(split_analyses) >= 4:
            break

    # --- even-split pace targets from goals ---
    goals = db.session.query(Goal).filter_by(user_id=user_id).order_by(Goal.created_at.desc()).all()
    target_splits = []
    for g in goals:
        target = g.target_seconds()
        dist = _event_distance(g.event)
        if not target or not dist or dist % 50 != 0:
            continue
        n50 = dist // 50
        if n50 < 2 or n50 > 30:
            continue
        per = target / n50
        rows = [{'idx': i + 1, 'split': _an_fmt(per), 'cum': _an_fmt(per * (i + 1))} for i in range(n50)]
        target_splits.append({
            'event': g.event,
            'target_time': g.target_time,
            'per50': _an_fmt(per),
            'rows': rows,
        })
        if len(target_splits) >= 4:
            break

    # --- personal baselines: the swimmer's own "normal", which sharpens as
    # more data comes in. This is the seed of a longer-term athlete model:
    # instead of generic benchmarks, everything is measured against THEM. ---
    from models import CheckIn
    baselines = []
    active_weeks = [w['vol'] for w in weeks if w['vol'] > 0]
    if active_weeks:
        baselines.append({
            'label': 'Typical week',
            'value': f"{round(sum(active_weeks) / len(active_weeks)):,}m",
            'sub': f"across {len(active_weeks)} active weeks",
        })
    swim_dates = {s.logged_at.date() for s in swims} | {s.logged_at.date() for s in sessions}
    if swim_dates:
        weeks_span = max(1, (max(swim_dates) - min(swim_dates)).days / 7)
        baselines.append({
            'label': 'Sessions / week',
            'value': f"{(len(sessions) + len(swims)) / weeks_span:.1f}",
            'sub': 'your usual rhythm',
        })

    checkins = db.session.query(CheckIn).filter_by(user_id=user_id).all()
    sleeps = [c.sleep_quality for c in checkins if c.sleep_quality]
    feels = [c.feeling_rating for c in checkins if c.feeling_rating]
    if sleeps:
        baselines.append({'label': 'Typical sleep', 'value': f"{sum(sleeps) / len(sleeps):.1f}/5", 'sub': f"from {len(sleeps)} check-ins"})
    if feels:
        baselines.append({'label': 'Typical energy', 'value': f"{sum(feels) / len(feels):.1f}/5", 'sub': 'how training usually feels'})

    # --- learned patterns: genuine correlations pulled from this swimmer's own
    # history. Deliberately gated behind a minimum sample so we never invent a
    # pattern from two data points. This is what "the AI learns you over time"
    # means in practice: these unlock as the log grows. ---
    patterns = []
    paired = [(c.sleep_quality, c.feeling_rating) for c in checkins if c.sleep_quality and c.feeling_rating]
    if len(paired) >= 6:
        good = [f for sl, f in paired if sl >= 4]
        poor = [f for sl, f in paired if sl <= 2]
        if good and poor:
            diff = sum(good) / len(good) - sum(poor) / len(poor)
            if diff >= 0.6:
                patterns.append(
                    f"You tend to feel better in training after good sleep, about {diff:.1f}/5 higher energy "
                    f"on well-slept days than poorly-slept ones. Protecting sleep before hard sets looks like it pays off for you."
                )
    if len([w for w in weeks if w['vol'] > 0]) >= 4:
        recent = [w['vol'] for w in weeks[-4:] if w['vol'] > 0]
        earlier = [w['vol'] for w in weeks[:-4] if w['vol'] > 0]
        if recent and earlier:
            r_avg, e_avg = sum(recent) / len(recent), sum(earlier) / len(earlier)
            if r_avg > e_avg * 1.25:
                patterns.append("Your training volume has stepped up recently. Keep an eye on how you recover, this is often when swimmers either break through or get run down.")
            elif r_avg < e_avg * 0.7:
                patterns.append("Your training volume has dropped off lately. If your times slip a little, that's the most likely reason rather than lost fitness.")

    return {
        'progression': progression,
        'comparison': comparison,
        'weeks': weeks,
        'total_12wk': total_12wk,
        'split_analyses': split_analyses,
        'target_splits': target_splits,
        'baselines': baselines,
        'patterns': patterns,
        'has_any': bool(progression or split_analyses or target_splits or total_12wk),
    }


@solo.route('/analytics')
@login_required
@solo_required
def analytics():
    from app import db
    from models import AthleteProfile

    data = _build_analytics(current_user.id)
    profile = db.session.query(AthleteProfile).filter_by(user_id=current_user.id).first()
    insight = profile.get_progress_insight() if profile else {}

    # The automatic 7-day review: generated lazily once a week has passed
    # since the last one, deterministic math with an optional AI narrative.
    import athlete_model
    weekly_report = athlete_model.ensure_weekly_report(
        current_user.id,
        api_key=current_app.config.get('ANTHROPIC_API_KEY'),
        model=current_app.config.get('ANTHROPIC_MODEL'),
        tone=(profile.coaching_tone if profile else 'encouraging'),
    )

    return render_template('solo_analytics.html', profile=profile, insight=insight,
                           weekly_report=weekly_report, **data)


@solo.route('/dryland')
@login_required
@solo_required
def dryland_library():
    from app import db
    from models import TrainingProgram

    programs = (
        db.session.query(TrainingProgram)
        .filter(TrainingProgram.category != 'Nutrition')
        .order_by(TrainingProgram.created_at.desc())
        .all()
    )
    return render_template('dryland_library.html', programs=programs)


@solo.route('/dryland/<int:program_id>')
@login_required
@solo_required
def dryland_view(program_id):
    from app import db
    from models import TrainingProgram

    p = db.session.query(TrainingProgram).get(program_id)
    if not p or p.category == 'Nutrition':
        abort(404)
    return render_template('program_view.html', p=p, back_url='/solo/dryland', back_label='Dryland library')


@solo.route('/nutrition')
@login_required
@solo_required
def nutrition_library():
    from nutrition_data import CATEGORIES, PRODUCTS, meals_by_category

    return render_template(
        'nutrition.html',
        categories=CATEGORIES,
        meals_by_cat=meals_by_category(),
        products=PRODUCTS,
    )


@solo.route('/nutrition/<int:program_id>')
@login_required
@solo_required
def nutrition_view(program_id):
    from app import db
    from models import TrainingProgram

    p = db.session.query(TrainingProgram).get(program_id)
    if not p or p.category != 'Nutrition':
        abort(404)
    return render_template('program_view.html', p=p, back_url='/solo/nutrition', back_label='Nutrition library')


def _injury_summary(injury):
    """Plain-text summary of an InjuryStatus row for the AI prompt, or None
    if there's nothing on file."""
    if not injury:
        return None
    parts = []
    for label, val in (('Shoulder', injury.shoulder), ('Knee', injury.knee), ('Back', injury.back), ('Other', injury.other)):
        if val and val.strip():
            parts.append(f"{label}: {val.strip()}")
    if not parts:
        return None
    flag = " [RED FLAG previously noted]" if injury.red_flag else ""
    return "; ".join(parts) + flag + f" (last updated {injury.updated_at.strftime('%d %b %Y') if injury.updated_at else 'unknown'})"


def _dryland_load(entries):
    """RPE x duration load signal from a swimmer's own DrylandLogEntry rows,
    see swim-coach/reference/load-management.md. `entries` must already be
    sorted/filtered to the swimmer, any order."""
    now = datetime.utcnow()
    acute = sum(e.session_load() for e in entries if e.logged_at and (now - e.logged_at).days < 7)
    chronic_total = sum(e.session_load() for e in entries if e.logged_at and (now - e.logged_at).days < 28)
    chronic_weekly = chronic_total / 4.0
    acwr = round(acute / chronic_weekly, 2) if chronic_weekly > 0 else None
    return {'acute': acute, 'chronic_weekly': round(chronic_weekly), 'acwr': acwr, 'entries_count': len(entries)}


@solo.route('/coach')
@login_required
@solo_required
def coach():
    from app import db
    from models import AthleteProfile, CoachMessage, InjuryStatus, DrylandLogEntry
    import athlete_model

    topic = request.args.get('topic', 'nutrition')
    if topic not in ('nutrition', 'dryland'):
        topic = 'nutrition'

    profile = db.session.query(AthleteProfile).filter_by(user_id=current_user.id).first()
    messages = (
        db.session.query(CoachMessage)
        .filter_by(user_id=current_user.id, topic=topic)
        .order_by(CoachMessage.created_at.asc())
        .limit(40)
        .all()
    )
    injury = db.session.query(InjuryStatus).filter_by(user_id=current_user.id).first()
    dryland_entries = (
        db.session.query(DrylandLogEntry)
        .filter_by(user_id=current_user.id)
        .order_by(DrylandLogEntry.logged_at.desc())
        .limit(10)
        .all()
    )
    pool_state = athlete_model.get_state(current_user.id)

    needs_injury_check = topic == 'dryland' and (not injury or injury.is_stale())

    return render_template(
        'solo_coach.html', topic=topic, profile=profile, messages=messages,
        injury=injury, dryland_entries=dryland_entries, pool_state=pool_state,
        needs_injury_check=needs_injury_check,
    )


@solo.route('/coach/message', methods=['POST'])
@login_required
@solo_required
def coach_message():
    from app import db
    from models import AthleteProfile, CoachMessage, InjuryStatus, DrylandLogEntry
    from validation import clean_text
    import athlete_model

    if not current_app.config.get('ANTHROPIC_API_KEY'):
        return jsonify({'ok': False, 'error': "AI coach isn't set up yet."}), 503

    data = request.get_json(silent=True) or {}
    topic = data.get('topic')
    if topic not in ('nutrition', 'dryland'):
        return jsonify({'ok': False, 'error': 'Invalid topic.'}), 400

    message = clean_text(data.get('message'), 2000)
    if not message:
        return jsonify({'ok': False, 'error': 'Type a message first.'}), 400

    profile = db.session.query(AthleteProfile).filter_by(user_id=current_user.id).first()
    injury = db.session.query(InjuryStatus).filter_by(user_id=current_user.id).first()
    dryland_entries = (
        db.session.query(DrylandLogEntry).filter_by(user_id=current_user.id).all()
        if topic == 'dryland' else []
    )
    pool_state = athlete_model.get_state(current_user.id)
    dryland_load = _dryland_load(dryland_entries) if topic == 'dryland' else None

    history_rows = (
        db.session.query(CoachMessage)
        .filter_by(user_id=current_user.id, topic=topic)
        .order_by(CoachMessage.created_at.desc())
        .limit(12)
        .all()
    )
    history = [{'role': m.role, 'content': m.content} for m in reversed(history_rows)]

    from ai_utils import generate_coach_chat_reply
    reply = generate_coach_chat_reply(
        topic, message, profile, pool_state, _injury_summary(injury), dryland_load, history,
        current_app.config['ANTHROPIC_API_KEY'], current_app.config['ANTHROPIC_MODEL'],
    )

    db.session.add(CoachMessage(user_id=current_user.id, topic=topic, role='user', content=message))
    db.session.add(CoachMessage(user_id=current_user.id, topic=topic, role='assistant', content=reply))
    db.session.commit()

    return jsonify({'ok': True, 'reply': reply})


@solo.route('/coach/injury', methods=['POST'])
@login_required
@solo_required
def coach_injury():
    from app import db
    from models import InjuryStatus
    from validation import clean_text

    injury = db.session.query(InjuryStatus).filter_by(user_id=current_user.id).first() or \
        InjuryStatus(user_id=current_user.id)
    injury.shoulder = clean_text(request.form.get('shoulder'), 300) or 'None'
    injury.knee = clean_text(request.form.get('knee'), 300) or 'None'
    injury.back = clean_text(request.form.get('back'), 300) or 'None'
    injury.other = clean_text(request.form.get('other'), 300) or 'None'
    injury.red_flag = request.form.get('red_flag') == '1'
    injury.updated_at = datetime.utcnow()
    if not injury.id:
        db.session.add(injury)
    db.session.commit()

    if injury.red_flag:
        flash("That sounds like something to get checked by a physio or clinician before doing more dryland work — hold off on training that area for now.", 'error')
    else:
        flash('Injury status updated.', 'success')
    return redirect(url_for('solo.coach', topic='dryland'))


@solo.route('/coach/log-dryland', methods=['POST'])
@login_required
@solo_required
def coach_log_dryland():
    from app import db
    from models import DrylandLogEntry
    from validation import clean_int, clean_text

    rpe = clean_int(request.form.get('rpe'), lo=1, hi=10)
    duration = clean_int(request.form.get('duration_minutes'), key='duration_minutes')
    if not rpe or not duration:
        flash('RPE (1-10) and duration are needed to log a session.', 'error')
        return redirect(url_for('solo.coach', topic='dryland'))

    entry = DrylandLogEntry(
        user_id=current_user.id,
        focus=clean_text(request.form.get('focus'), 120) or 'Dryland session',
        rpe=rpe,
        duration_minutes=duration,
        pain_notes=clean_text(request.form.get('pain_notes'), 500),
    )
    db.session.add(entry)
    db.session.commit()
    flash('Dryland session logged.', 'success')
    return redirect(url_for('solo.coach', topic='dryland'))


@solo.route('/leaderboard-optin', methods=['GET', 'POST'])
@login_required
@solo_required
def leaderboard_optin():
    from app import db

    if request.method == 'POST':
        current_user.share_leaderboard = not current_user.share_leaderboard
        db.session.commit()
        flash('Leaderboard sharing turned ' + ('on' if current_user.share_leaderboard else 'off') + '.', 'success')
        return redirect(url_for('solo.leaderboard'))

    return redirect(url_for('solo.leaderboard'))


@solo.route('/leaderboard')
@login_required
@solo_required
def leaderboard():
    from app import db
    from models import Swim, User

    event = request.args.get('event', '')

    opted_in_users = db.session.query(User).filter_by(share_leaderboard=True).all()
    opted_in_ids = [u.id for u in opted_in_users]
    names = {u.id: u.username for u in opted_in_users}

    swims = (
        db.session.query(Swim)
        .filter(Swim.user_id.in_(opted_in_ids))
        .all()
        if opted_in_ids else []
    )

    events = sorted({s.event for s in swims})
    if not event and events:
        event = events[0]

    best_by_user = {}
    for s in swims:
        if s.event != event:
            continue
        secs = s.time_in_seconds()
        if secs is None:
            continue
        current = best_by_user.get(s.user_id)
        if current is None or secs < current['secs']:
            best_by_user[s.user_id] = {'swim': s, 'secs': secs}

    rows = sorted(best_by_user.values(), key=lambda r: r['secs'])
    for r in rows:
        r['username'] = names.get(r['swim'].user_id, 'Swimmer')

    return render_template(
        'leaderboard.html',
        events=events,
        event=event,
        rows=rows,
        opted_in=current_user.share_leaderboard,
    )
