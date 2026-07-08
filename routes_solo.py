from datetime import datetime, timedelta

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, jsonify, current_app
from flask_login import login_required, current_user

from auth_utils import solo_required

solo = Blueprint('solo', __name__, url_prefix='/solo')

MAX_SCAN_BYTES = 20 * 1024 * 1024  # raw phone-camera uploads before we downscale server-side
WEEKLY_REGEN_LIMIT = 3  # AI program rebuilds allowed per rolling week


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


@solo.route('/onboarding', methods=['GET', 'POST'])
@login_required
@solo_required
def onboarding():
    from app import db
    from models import AthleteProfile

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

        try:
            age = int(request.form.get('age') or 0) or None
        except ValueError:
            age = None
        try:
            training_days = int(request.form.get('training_days_per_week') or 0) or None
        except ValueError:
            training_days = None

        profile = existing or AthleteProfile(user_id=current_user.id)
        profile.level = request.form.get('level', '').strip()
        profile.age = age
        profile.training_days_per_week = training_days
        profile.fitness_ability = request.form.get('fitness_ability', '').strip()
        profile.primary_stroke = request.form.get('primary_stroke', '').strip()
        profile.main_goal = request.form.get('main_goal', '').strip()

        # AI tuning is a Solo Pro feature; free solo swimmers stay on the
        # defaults no matter what gets posted.
        if current_user.is_solo_pro:
            tone = request.form.get('coaching_tone', 'balanced')
            profile.coaching_tone = tone if tone in ('encouraging', 'balanced', 'direct') else 'balanced'
            intensity = request.form.get('intensity', 'normal')
            profile.intensity = intensity if intensity in ('easier', 'normal', 'harder') else 'normal'
        else:
            profile.coaching_tone = 'balanced'
            profile.intensity = 'normal'

        profile.updated_at = datetime.utcnow()

        from ai_utils import generate_training_program
        result = generate_training_program(
            profile,
            current_app.config['ANTHROPIC_API_KEY'],
            current_app.config['ANTHROPIC_MODEL'],
        )
        if not result.get('ok'):
            flash(result.get('error', "Couldn't generate a program — try again."), 'error')
            return redirect(url_for('solo.onboarding'))

        import json
        profile.program_json = json.dumps(result['program'])
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
    from models import AthleteProfile

    profile = db.session.query(AthleteProfile).filter_by(user_id=current_user.id).first()
    if not profile or not profile.program_json:
        return redirect(url_for('solo.onboarding'))

    return render_template(
        'solo_program.html', profile=profile, program=profile.get_program(),
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

        try:
            feeling = int(request.form.get('feeling_rating') or 0)
        except ValueError:
            feeling = 0
        notes = request.form.get('notes', '').strip()
        if feeling < 1 or feeling > 5:
            flash('Rate how you felt from 1 to 5.', 'error')
            return redirect(url_for('solo.checkin'))

        recent = (
            db.session.query(CheckIn)
            .filter_by(user_id=current_user.id)
            .order_by(CheckIn.checkin_date.desc())
            .limit(7)
            .all()
        )
        recent_for_ai = [
            {'date': c.checkin_date.isoformat(), 'feeling_rating': c.feeling_rating, 'notes': c.notes or ''}
            for c in reversed(recent)
        ]

        from ai_utils import generate_checkin_insight
        insight = generate_checkin_insight(
            profile, feeling, notes, recent_for_ai,
            current_app.config['ANTHROPIC_API_KEY'],
            current_app.config['ANTHROPIC_MODEL'],
        )

        existing_today = (
            db.session.query(CheckIn)
            .filter_by(user_id=current_user.id, checkin_date=today)
            .first()
        )
        entry = existing_today or CheckIn(user_id=current_user.id, checkin_date=today)
        entry.feeling_rating = feeling
        entry.notes = notes
        entry.ai_insight = insight
        if not existing_today:
            db.session.add(entry)
        db.session.commit()
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

    return render_template(
        'solo_checkin.html',
        profile=profile,
        todays_checkin=todays_checkin,
        history=history,
    )


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
    from nutrition_data import CATEGORIES, meals_by_category

    return render_template(
        'nutrition.html',
        categories=CATEGORIES,
        meals_by_cat=meals_by_category(),
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
