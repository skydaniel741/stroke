from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, jsonify, current_app
from flask_login import login_required, current_user

from auth_utils import solo_required

solo = Blueprint('solo', __name__, url_prefix='/solo')

MAX_SCAN_BYTES = 20 * 1024 * 1024  # raw phone-camera uploads before we downscale server-side


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
    from app import db
    from models import TrainingProgram

    programs = (
        db.session.query(TrainingProgram)
        .filter_by(category='Nutrition')
        .order_by(TrainingProgram.created_at.desc())
        .all()
    )
    return render_template('nutrition_library.html', programs=programs)


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
