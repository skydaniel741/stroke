import json
import re
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime, timedelta

main = Blueprint('main', __name__)

SET_CATEGORIES = [
    {'key': 'Fast',       'slug': 'fast',        'label': 'Fast sets',        'blurb': 'Sprint speed & race pace',     'color': '#ff5a5f', 'icon': 'bolt'},
    {'key': 'Easy',       'slug': 'easy',        'label': 'Easy sets',        'blurb': 'Recovery & loosen up',          'color': '#4dd0e1', 'icon': 'feather'},
    {'key': 'Heart Rate', 'slug': 'heart-rate',  'label': 'Heart rate sets',  'blurb': 'Aerobic zone & threshold',      'color': '#ff4d6d', 'icon': 'heart'},
    {'key': 'Drill',      'slug': 'drill',       'label': 'Drill sets',       'blurb': 'Technique & stroke feel',       'color': '#ffb703', 'icon': 'target'},
    {'key': 'Lactate',    'slug': 'lactate',     'label': 'Lactate sets',     'blurb': 'High-intensity tolerance',      'color': '#fb8500', 'icon': 'flame'},
    {'key': 'Fitness',    'slug': 'fitness',     'label': 'Fitness sets',     'blurb': 'General conditioning',          'color': '#8f8ff0', 'icon': 'dumbbell'},
    {'key': 'Open Water', 'slug': 'open-water',  'label': 'Open water sets',  'blurb': 'Sighting, pacing, distance',    'color': '#219ebc', 'icon': 'waves'},
    {'key': 'Triathlon',  'slug': 'triathlon',   'label': 'Triathlon sets',   'blurb': 'CSS pace & race-ready swimming', 'color': '#2ec4b6', 'icon': 'tri'},
]

def _find_category(slug=None, key=None):
    for c in SET_CATEGORIES:
        if slug is not None and c['slug'] == slug:
            return c
        if key is not None and c['key'] == key:
            return c
    return None

STROKE_LABELS = {
    'FR': 'Freestyle', 'BK': 'Backstroke', 'BR': 'Breaststroke', 'FL': 'Butterfly',
    'IM': 'IM', 'Kick': 'Kick', 'Pull': 'Pull', 'Drill': 'Drill',
}

@main.route('/')
def home():
    return render_template('index.html')


@main.route('/privacy')
def privacy():
    return render_template('privacy.html')

@main.route('/signup', methods=['GET', 'POST'])
def signup():
    from app import db
    from models import User
    from email_utils import send_verification_email

    if request.method == 'POST':
        username = request.form.get('username').strip()
        email = request.form.get('email').strip().lower()
        password = request.form.get('password')

        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'error')
            return redirect(url_for('main.signup'))

        # FIXED: Changed from User.query to db.session.query(User)
        if db.session.query(User).filter_by(email=email).first():
            flash('An account with that email already exists.', 'error')
            return redirect(url_for('main.signup'))

        # FIXED: Changed from User.query to db.session.query(User)
        if db.session.query(User).filter_by(username=username).first():
            flash('That username is taken.', 'error')
            return redirect(url_for('main.signup'))

        user = User(email=email, username=username)
        user.set_password(password)
        code = user.generate_verify_code()
        db.session.add(user)
        db.session.commit()

        send_verification_email(email, username, code)
        return redirect(url_for('main.verify', email=email))

    return render_template('signup.html')

@main.route('/verify', methods=['GET', 'POST'])
def verify():
    from app import db
    from models import User

    email = request.args.get('email') or request.form.get('email')
    user = db.session.query(User).filter_by(email=email).first()

    if not user:
        return redirect(url_for('main.signup'))

    if request.method == 'POST':
        code = request.form.get('code').strip()

        if not user.verify_code or not user.verify_code_sent_at:
            flash('No code found. Please sign up again.', 'error')
            return redirect(url_for('main.signup'))

        code_age = datetime.utcnow() - user.verify_code_sent_at
        if code_age > timedelta(minutes=15):
            flash('Code expired. Request a new one.', 'error')
            return render_template('verify.html', email=email)

        if code == user.verify_code:
            user.is_verified = True
            user.verify_code = None
            db.session.commit()
            login_user(user)
            flash('Email verified. Welcome to STROKE!', 'success')
            return redirect(url_for('main.dashboard'))
        else:
            flash('Incorrect code. Try again.', 'error')
            return render_template('verify.html', email=email)

    return render_template('verify.html', email=email)

@main.route('/resend-code')
def resend_code():
    from app import db
    from models import User
    from email_utils import send_verification_email

    email = request.args.get('email')
    user = db.session.query(User).filter_by(email=email).first()

    if user and not user.is_verified:
        code = user.generate_verify_code()
        db.session.commit()
        send_verification_email(email, user.username, code)
        flash('New code sent.', 'success')

    return redirect(url_for('main.verify', email=email))

@main.route('/login', methods=['GET', 'POST'])
def login():
    from app import db
    from models import User

    if request.method == 'POST':
        email = request.form.get('email').strip().lower()
        password = request.form.get('password')
        user = db.session.query(User).filter_by(email=email).first()
        
        if not user:
            flash('No account found with that email.', 'error')
            return redirect(url_for('main.login'))

        if user.check_password(password):
            if not user.is_verified:
                flash('Please verify your email first.', 'error')
                return redirect(url_for('main.verify', email=email))
            login_user(user)
            if user.is_admin:
                return redirect(url_for('main.admin_dashboard'))
            return redirect(url_for('main.dashboard'))
        else:
            flash('Incorrect email or password.', 'error')
            return redirect(url_for('main.login'))

    return render_template('login.html')

def _oauth_login_or_create(email, display_name):
    """Find an existing user by email or create a fresh, already-verified
    account (the provider has verified the email). Returns the user."""
    import secrets
    from app import db
    from models import User

    email = (email or '').strip().lower()
    if not email:
        return None

    user = db.session.query(User).filter_by(email=email).first()
    if user:
        if not user.is_verified:
            user.is_verified = True
            db.session.commit()
        return user

    base = ''.join(c for c in (display_name or email.split('@')[0]).lower() if c.isalnum()) or 'swimmer'
    username = base
    n = 1
    while db.session.query(User).filter_by(username=username).first():
        n += 1
        username = f'{base}{n}'

    user = User(email=email, username=username, is_verified=True)
    # Social accounts have no usable password; store a random one so the
    # column stays non-null and password login stays impossible to guess.
    user.set_password(secrets.token_urlsafe(32))
    db.session.add(user)
    db.session.commit()
    return user


@main.route('/auth/<provider>')
def oauth_start(provider):
    from flask import current_app
    from extension import oauth

    if provider not in ('google', 'apple'):
        return redirect(url_for('main.login'))

    if not current_app.config.get(f'{provider.upper()}_AUTH_ENABLED'):
        flash(f"{provider.capitalize()} sign-in isn't set up yet — use email and password for now.", 'error')
        return redirect(url_for('main.login'))

    client = oauth.create_client(provider)
    redirect_uri = url_for('main.oauth_callback', provider=provider, _external=True)
    return client.authorize_redirect(redirect_uri)


@main.route('/auth/<provider>/callback', methods=['GET', 'POST'])
def oauth_callback(provider):
    from flask import current_app
    from extension import oauth

    if provider not in ('google', 'apple') or not current_app.config.get(f'{provider.upper()}_AUTH_ENABLED'):
        return redirect(url_for('main.login'))

    client = oauth.create_client(provider)
    try:
        token = client.authorize_access_token()
    except Exception:
        flash('Sign-in was cancelled or failed — try again.', 'error')
        return redirect(url_for('main.login'))

    userinfo = token.get('userinfo') or {}
    email = userinfo.get('email')
    name = userinfo.get('given_name') or userinfo.get('name')

    user = _oauth_login_or_create(email, name)
    if not user:
        flash("We couldn't read an email address from that account.", 'error')
        return redirect(url_for('main.login'))

    login_user(user)
    if user.is_admin:
        return redirect(url_for('main.admin_dashboard'))
    return redirect(url_for('main.dashboard'))


@main.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.home'))

@main.route('/dashboard')
@login_required
def dashboard():
    from app import db
    from models import Swim, Session, Announcement, SquadMembership, AthleteProfile, SquadEvent, Squad
    from datetime import timedelta

    needs_ai_onboarding = False
    if current_user.is_solo:
        has_profile = db.session.query(AthleteProfile).filter_by(user_id=current_user.id).first()
        needs_ai_onboarding = has_profile is None

    site_announcement = (
        db.session.query(Announcement)
        .filter_by(squad_id=None)
        .order_by(Announcement.created_at.desc())
        .first()
    )

    my_squad_ids = [
        m.squad_id for m in
        db.session.query(SquadMembership).filter_by(user_id=current_user.id, status='active').all()
    ]
    squad_announcements = (
        db.session.query(Announcement)
        .filter(Announcement.squad_id.in_(my_squad_ids))
        .order_by(Announcement.created_at.desc())
        .limit(5)
        .all()
        if my_squad_ids else []
    )

    # --- squad schedule: today's + upcoming coach-planned sessions ---
    today_date = datetime.utcnow().date()
    squad_events = (
        db.session.query(SquadEvent)
        .filter(
            SquadEvent.squad_id.in_(my_squad_ids),
            SquadEvent.event_date >= today_date,
            SquadEvent.event_date <= today_date + timedelta(days=6),
        )
        .order_by(SquadEvent.event_date, SquadEvent.slot, SquadEvent.event_time)
        .all()
        if my_squad_ids else []
    )
    squad_names = {
        s.id: s.name for s in
        (db.session.query(Squad).filter(Squad.id.in_(my_squad_ids)).all() if my_squad_ids else [])
    }
    todays_squad_sessions = [e for e in squad_events if e.event_date == today_date]
    upcoming_squad_sessions = [e for e in squad_events if e.event_date != today_date][:4]

    swims = db.session.query(Swim).filter_by(user_id=current_user.id).order_by(Swim.logged_at.desc()).all()
    sessions = db.session.query(Session).filter_by(user_id=current_user.id).order_by(Session.logged_at.desc()).all()

    # --- this week's stats ---
    now = datetime.utcnow()
    week_start = now - timedelta(days=now.weekday())  # Monday 00:00
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)

    sessions_this_week = [s for s in sessions if s.logged_at >= week_start]
    swims_this_week = [s for s in swims if s.logged_at >= week_start]

    volume_this_week = (
        sum(s.total_distance() for s in sessions_this_week) +
        sum(s.distance() for s in swims_this_week)
    )
    sessions_logged_count = len(sessions_this_week) + len(swims_this_week)

    # --- streak: consecutive days (including today) with at least one log ---
    all_dates = sorted(set(
        [s.logged_at.date() for s in swims] + [s.logged_at.date() for s in sessions]
    ), reverse=True)

    streak = 0
    if all_dates:
        expected = now.date()
        for d in all_dates:
            if d == expected:
                streak += 1
                expected -= timedelta(days=1)
            elif d == expected + timedelta(days=1):
                continue  # shouldn't happen given sort, safety only
            else:
                break

    # --- last 8 weeks volume + session count, for the bar chart ---
    weekly_volume = []
    weekly_sessions = []
    for i in range(7, -1, -1):
        wk_start = week_start - timedelta(weeks=i)
        wk_end = wk_start + timedelta(days=7)
        wk_sessions_in_range = [s for s in sessions if wk_start <= s.logged_at < wk_end]
        wk_swims_in_range = [s for s in swims if wk_start <= s.logged_at < wk_end]
        weekly_volume.append(
            sum(s.total_distance() for s in wk_sessions_in_range) +
            sum(s.distance() for s in wk_swims_in_range)
        )
        weekly_sessions.append(len(wk_sessions_in_range) + len(wk_swims_in_range))

    max_week = max(weekly_volume) if any(weekly_volume) else 1
    max_week_sessions = max(weekly_sessions) if any(weekly_sessions) else 1

    # --- pool split: real % of volume swum short course vs long course ---
    pool_dist = {'25': 0, '50': 0}
    for s in sessions:
        key = '50' if str(s.pool).startswith('50') else '25'
        pool_dist[key] += s.total_distance()
    for s in swims:
        key = '50' if str(s.pool).startswith('50') else '25'
        pool_dist[key] += s.distance()
    total_pool_dist = pool_dist['25'] + pool_dist['50']
    has_pool_data = total_pool_dist > 0
    pool_split_25 = round(pool_dist['25'] / total_pool_dist * 100) if has_pool_data else 0
    pool_split_50 = 100 - pool_split_25 if has_pool_data else 0

    # --- recent activity feed: swims + sessions, merged and sorted ---
    recent_activity = sorted(
        [
            {
                'kind': 'PB',
                'label': s.event,
                'pool': s.pool or '—',
                'logged_at': s.logged_at,
                'type': 'swim',
                'id': s.id,
            } for s in swims
        ] + [
            {
                'kind': s.session_type or 'Session',
                'label': f"{len(s.get_sets())} set" + ('s' if len(s.get_sets()) != 1 else '') if s.get_sets() else (s.session_type or 'Session'),
                'pool': s.pool or '—',
                'logged_at': s.logged_at,
                'type': 'session',
                'id': s.id,
            } for s in sessions
        ],
        key=lambda x: x['logged_at'],
        reverse=True
    )[:5]

    # --- personal bests: fastest time per event ---
    best_by_event = {}
    for s in swims:
        secs = s.time_in_seconds()
        if secs is None:
            continue
        current = best_by_event.get(s.event)
        if current is None or secs < current['secs']:
            best_by_event[s.event] = {'event': s.event, 'time': s.time, 'pool': s.pool, 'secs': secs}
    personal_bests = sorted(best_by_event.values(), key=lambda x: x['secs'])[:5]

    # --- last 21 days, for the streak grid ---
    logged_dates = set(all_dates)
    today = now.date()
    streak_days = [
        {'done': (today - timedelta(days=i)) in logged_dates, 'today': i == 0}
        for i in range(20, -1, -1)
    ]

    # --- on this day: same month/day, a prior year ---
    on_this_day = [
        s for s in swims
        if s.logged_at.month == today.month and s.logged_at.day == today.day and s.logged_at.year != today.year
    ]

    # --- gentle rest-day nudge: long unbroken streaks only ---
    show_rest_nudge = streak >= 6

    return render_template(
        'dashboard.html',
        on_this_day=on_this_day,
        show_rest_nudge=show_rest_nudge,
        site_announcement=site_announcement,
        squad_announcements=squad_announcements,
        swims=swims,
        sessions=sessions,
        sessions_this_week=sessions_logged_count,
        volume_this_week=volume_this_week,
        streak=streak,
        weekly_volume=weekly_volume,
        weekly_sessions=weekly_sessions,
        max_week=max_week,
        max_week_sessions=max_week_sessions,
        recent_activity=recent_activity,
        personal_bests=personal_bests,
        streak_days=streak_days,
        has_pool_data=has_pool_data,
        pool_split_25=pool_split_25,
        pool_split_50=pool_split_50,
        needs_ai_onboarding=needs_ai_onboarding,
        todays_squad_sessions=todays_squad_sessions,
        upcoming_squad_sessions=upcoming_squad_sessions,
        squad_names=squad_names,
    )



@main.route('/log', methods=['GET', 'POST'])
@login_required
def log():
    from app import db
    from models import Swim, Session, SavedSet

    if request.method == 'POST':
        log_type = request.form.get('log_type')
        notes = request.form.get('notes', '')

        if log_type == 'pb':
            # Save a PB / race time
            splits_raw = request.form.get('splits', '[]')
            try:
                splits_list = json.loads(splits_raw)
                if not isinstance(splits_list, list):
                    splits_list = []
            except ValueError:
                splits_list = []

            swim = Swim(
                user_id=current_user.id,
                event=request.form.get('event'),
                pool=request.form.get('pool'),
                stroke=request.form.get('stroke'),
                time=request.form.get('time'),
                notes=notes,
                tag=request.form.get('tag', 'practice'),
                splits=json.dumps(splits_list) if splits_list else None,
                logged_at=datetime.utcnow()
            )
            db.session.add(swim)
            db.session.commit()
            flash('PB logged!', 'success')

        elif log_type == 'session':
            # Save a full training session
            session_data = request.form.get('session_data', '[]')
            session = Session(
                user_id=current_user.id,
                session_type=request.form.get('event'),
                pool=request.form.get('pool'),
                sets_data=session_data,
                notes=notes,
                logged_at=datetime.utcnow()
            )
            db.session.add(session)
            db.session.commit()
            flash('Session logged!', 'success')

        return redirect(url_for('main.dashboard'))

    last_session = (
        db.session.query(Session)
        .filter_by(user_id=current_user.id)
        .order_by(Session.logged_at.desc())
        .first()
    )

    preload_set = None
    use_id = request.args.get('use')
    use_session_id = request.args.get('use_session')
    if use_id:
        picked = db.session.query(SavedSet).get(use_id)
        if picked:
            try:
                blocks = json.loads(picked.sets_data or '[]')
            except ValueError:
                blocks = []
            preload_set = {
                'pool': picked.pool,
                'session_type': picked.session_type,
                'blocks': blocks
            }
    elif use_session_id:
        picked_session = db.session.query(Session).get(use_session_id)
        if picked_session and picked_session.user_id == current_user.id:
            preload_set = {
                'pool': picked_session.pool,
                'session_type': picked_session.session_type,
                'blocks': picked_session.get_sets(),
            }

    return render_template(
        'log.html',
        last_session=last_session,
        preload_set=preload_set
    )


@main.route('/sets')
@login_required
def sets_library():
    from app import db
    from models import SavedSet

    saved_sets = db.session.query(SavedSet).all()
    categories = []
    for c in SET_CATEGORIES:
        count = sum(1 for s in saved_sets if (s.category or 'Fitness') == c['key'])
        categories.append({**c, 'count': count})

    return render_template('sets_library.html', categories=categories)


@main.route('/sets/category/<slug>')
@login_required
def sets_category(slug):
    from app import db
    from models import SavedSet
    from flask import abort

    category = _find_category(slug=slug)
    if not category:
        abort(404)

    sets = (
        db.session.query(SavedSet)
        .filter_by(category=category['key'])
        .order_by(SavedSet.created_at.desc())
        .all()
    )
    return render_template('sets_category.html', category=category, sets=sets)


@main.route('/sets/view/<int:set_id>')
@login_required
def sets_view(set_id):
    import json
    from app import db
    from models import SavedSet
    from flask import abort

    s = db.session.query(SavedSet).get(set_id)
    if not s:
        abort(404)

    category = _find_category(key=(s.category or 'Fitness')) or SET_CATEGORIES[5]
    try:
        blocks = json.loads(s.sets_data or '[]')
    except ValueError:
        blocks = []

    # Group blocks into workout sections in canonical order. Older sets
    # without a section field all land in "Main set".
    section_order = ['Warm up', 'Pre set', 'Main set', 'Sub set', 'Cool down']
    sections = []
    for name in section_order:
        sec_blocks = [b for b in blocks if b.get('section', 'Main set') == name]
        if sec_blocks:
            dist = sum(
                (int(b.get('reps', 0) or 0)) * (int(b.get('dist', 0) or 0))
                for b in sec_blocks
            )
            sections.append({'name': name, 'blocks': sec_blocks, 'distance': dist})

    return render_template(
        'sets_view.html',
        s=s, category=category, blocks=blocks, sections=sections,
        stroke_labels=STROKE_LABELS
    )


@main.route('/sets/create', methods=['POST'])
@login_required
def sets_create():
    from app import db
    from models import SavedSet

    name = (request.form.get('name') or '').strip()
    pool = request.form.get('pool', '25m')
    session_type = request.form.get('session_type', 'Training')
    sets_data = request.form.get('sets_data', '[]')
    category = request.form.get('category', 'Fitness')
    description = (request.form.get('description') or '').strip()

    if not name:
        return {'ok': False, 'error': 'Set needs a name.'}, 400

    new_set = SavedSet(
        name=name,
        pool=pool,
        session_type=session_type,
        sets_data=sets_data,
        category=category,
        description=description,
        created_by=current_user.id
    )
    db.session.add(new_set)
    db.session.commit()
    return {'ok': True, 'id': new_set.id, 'name': new_set.name, 'category': new_set.category}


@main.route('/sets/delete/<int:set_id>', methods=['POST'])
@login_required
def sets_delete(set_id):
    from app import db
    from models import SavedSet

    s = db.session.query(SavedSet).get(set_id)
    if s and (s.created_by == current_user.id or current_user.is_admin):
        db.session.delete(s)
        db.session.commit()
        flash('Set deleted.', 'success')
    return redirect(url_for('main.log'))


@main.route('/wa-points')
@login_required
def wa_points():
    return render_template('wa_points.html')


@main.route('/history')
@login_required
def history():
    from app import db
    from models import Swim, Session

    swims = db.session.query(Swim).filter_by(user_id=current_user.id).all()
    sessions = db.session.query(Session).filter_by(user_id=current_user.id).all()

    entries = sorted(
        [
            {
                'type': 'swim',
                'id': s.id,
                'kind': 'PB',
                'label': s.event,
                'pool': s.pool or '—',
                'tag': s.tag or 'practice',
                'logged_at': s.logged_at,
            } for s in swims
        ] + [
            {
                'type': 'session',
                'id': s.id,
                'kind': s.session_type or 'Session',
                'label': f"{len(s.get_sets())} set" + ('s' if len(s.get_sets()) != 1 else '') if s.get_sets() else (s.session_type or 'Session'),
                'pool': s.pool or '—',
                'distance': s.total_distance(),
                'logged_at': s.logged_at,
            } for s in sessions
        ],
        key=lambda x: x['logged_at'],
        reverse=True,
    )

    PER_PAGE = 25
    page = max(1, request.args.get('page', 1, type=int))
    total_pages = max(1, (len(entries) + PER_PAGE - 1) // PER_PAGE)
    page = min(page, total_pages)
    start = (page - 1) * PER_PAGE
    page_entries = entries[start:start + PER_PAGE]

    return render_template(
        'history.html',
        entries=page_entries,
        page=page,
        total_pages=total_pages,
        total_count=len(entries),
    )


@main.route('/history/session/<int:session_id>')
@login_required
def history_session(session_id):
    from app import db
    from models import Session

    session_log = db.session.query(Session).get(session_id)
    if not session_log or session_log.user_id != current_user.id:
        abort(404)

    blocks = session_log.get_sets()
    sections = []
    for b in blocks:
        sec_name = b.get('section', 'Main set')
        if sections and sections[-1]['name'] == sec_name:
            sections[-1]['blocks'].append(b)
            sections[-1]['distance'] += int(b.get('reps', 0)) * int(b.get('dist', 0))
        else:
            sections.append({
                'name': sec_name,
                'blocks': [b],
                'distance': int(b.get('reps', 0)) * int(b.get('dist', 0)),
            })

    return render_template('history_session.html', s=session_log, sections=sections, stroke_labels=STROKE_LABELS)


@main.route('/personal-bests')
@login_required
def personal_bests():
    from app import db
    from models import Swim, Standard

    q = request.args.get('q', '').strip().lower()
    pool_filter = request.args.get('pool', '')
    tag_filter = request.args.get('tag', '')

    swims = (
        db.session.query(Swim)
        .filter_by(user_id=current_user.id)
        .order_by(Swim.logged_at.desc())
        .all()
    )

    def _pool_key(p):
        return '50' if str(p or '25').startswith('50') else '25'

    filtered = swims
    if q:
        filtered = [s for s in filtered if q in (s.event or '').lower()]
    if pool_filter:
        filtered = [s for s in filtered if _pool_key(s.pool) == _pool_key(pool_filter)]
    if tag_filter:
        filtered = [s for s in filtered if (s.tag or 'practice') == tag_filter]

    # Best time per event across ALL swims (not just the filtered set).
    best_by_event = {}
    for s in swims:
        secs = s.time_in_seconds()
        if secs is None:
            continue
        current = best_by_event.get(s.event)
        if current is None or secs < current['secs']:
            best_by_event[s.event] = {'swim': s, 'secs': secs}

    standards = db.session.query(Standard).all()

    def nearest_standard(event, pool, secs):
        candidates = [st for st in standards if st.event == event and _pool_key(st.pool) == _pool_key(pool)]
        best = None
        for st in candidates:
            cutoff = st.cutoff_seconds()
            if cutoff is None:
                continue
            diff = secs - cutoff
            if best is None or abs(diff) < abs(best[1]):
                best = (st, diff)
        return best

    pb_rows = []
    for event, data in best_by_event.items():
        swim = data['swim']
        match = nearest_standard(event, swim.pool, data['secs'])
        pb_rows.append({
            'swim': swim,
            'standard': match[0] if match else None,
            'diff': round(match[1], 2) if match else None,
        })
    pb_rows.sort(key=lambda r: r['swim'].event)

    def _fmt_secs(secs):
        if secs >= 60:
            return f'{int(secs // 60)}:{secs % 60:05.2f}'
        return f'{secs:.2f}'

    # --- training trends: per event, recent form vs earlier form ---
    # Needs 4+ timed swims in an event. Compares the average of the newest
    # half against the oldest half; swimming is a sport of hundredths, so
    # anything past ±0.4% counts as a real move.
    swims_by_event = {}
    for s in swims:  # already newest-first
        secs = s.time_in_seconds()
        if secs is not None:
            swims_by_event.setdefault(s.event, []).append(secs)

    trend_rows = []
    for event, times in swims_by_event.items():
        if len(times) < 4:
            continue
        half = len(times) // 2
        recent_avg = sum(times[:half]) / half
        earlier_avg = sum(times[-half:]) / half
        change_pct = (recent_avg - earlier_avg) / earlier_avg * 100
        direction = 'improving' if change_pct < -0.4 else 'slipping' if change_pct > 0.4 else 'steady'
        trend_rows.append({
            'event': event,
            'count': len(times),
            'recent_avg': _fmt_secs(recent_avg),
            'change_pct': round(abs(change_pct), 1),
            'direction': direction,
        })
    trend_rows.sort(key=lambda r: {'slipping': 0, 'improving': 1, 'steady': 2}[r['direction']])

    # --- predicted times: Riegel's endurance model (t2 = t1 * (d2/d1)^1.06),
    # the same formula behind most race-time calculators. Trained on race
    # data across distances; a solid guide for training targets. ---
    def _event_parts(event):
        m = re.match(r'\s*(\d+)\s*m?\s+(.+)', event or '')
        return (int(m.group(1)), m.group(2).strip()) if m else (None, None)

    stroke_bests = {}
    for event, data in best_by_event.items():
        dist, stroke_name = _event_parts(event)
        if not dist or not stroke_name:
            continue
        cur = stroke_bests.setdefault(stroke_name, {})
        cur[dist] = min(cur.get(dist, float('inf')), data['secs'])

    PREDICT_DISTANCES = {
        'Freestyle': [50, 100, 200, 400, 800, 1500],
        'Backstroke': [50, 100, 200],
        'Breaststroke': [50, 100, 200],
        'Butterfly': [50, 100, 200],
        'IM': [100, 200, 400],
    }
    prediction_rows = []
    for stroke_name, bests in stroke_bests.items():
        targets = PREDICT_DISTANCES.get(stroke_name)
        if not targets:
            continue
        for target in targets:
            if target in bests:
                continue
            # Predict from the nearest distance we actually have a time for.
            base_dist = min(bests.keys(), key=lambda d: abs(d - target))
            # Riegel drifts badly past ~4x extrapolation; skip those.
            if not (0.25 <= target / base_dist <= 4):
                continue
            predicted = bests[base_dist] * (target / base_dist) ** 1.06
            prediction_rows.append({
                'event': f'{target}m {stroke_name}',
                'predicted': _fmt_secs(predicted),
                'base_event': f'{base_dist}m {stroke_name}',
                'base_time': _fmt_secs(bests[base_dist]),
            })
    prediction_rows.sort(key=lambda r: r['event'])

    return render_template(
        'personal_bests.html',
        pb_rows=pb_rows,
        swims=filtered,
        q=request.args.get('q', ''),
        pool_filter=pool_filter,
        tag_filter=tag_filter,
        trend_rows=trend_rows,
        prediction_rows=prediction_rows,
    )


@main.route('/personal-bests/export.csv')
@login_required
def personal_bests_export():
    import csv
    import io
    from flask import Response
    from app import db
    from models import Swim

    swims = (
        db.session.query(Swim)
        .filter_by(user_id=current_user.id)
        .order_by(Swim.logged_at.desc())
        .all()
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['event', 'pool', 'stroke', 'time', 'tag', 'splits', 'notes', 'logged_at'])
    for s in swims:
        writer.writerow([
            s.event, s.pool, s.stroke, s.time, s.tag or 'practice',
            ';'.join(s.get_splits()), s.notes or '', s.logged_at.strftime('%Y-%m-%d %H:%M'),
        ])

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=stroke_swim_history.csv'},
    )


@main.route('/personal-bests/import', methods=['POST'])
@login_required
def personal_bests_import():
    import csv
    import io
    from app import db
    from models import Swim

    file = request.files.get('csv_file')
    if not file or not file.filename:
        flash('Choose a CSV file first.', 'error')
        return redirect(url_for('main.personal_bests'))

    try:
        text = file.stream.read().decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(text))
        count = 0
        for row in reader:
            event = (row.get('event') or '').strip()
            time = (row.get('time') or '').strip()
            if not event or not time:
                continue
            splits_raw = (row.get('splits') or '').strip()
            splits_list = [x.strip() for x in splits_raw.split(';') if x.strip()] if splits_raw else []
            swim = Swim(
                user_id=current_user.id,
                event=event,
                pool=(row.get('pool') or '25m').strip(),
                stroke=(row.get('stroke') or '').strip(),
                time=time,
                tag=(row.get('tag') or 'practice').strip(),
                splits=json.dumps(splits_list) if splits_list else None,
                notes=(row.get('notes') or '').strip(),
            )
            db.session.add(swim)
            count += 1
        db.session.commit()
        flash(f'Imported {count} swim(s).', 'success')
    except Exception:
        flash('Could not read that CSV — check it matches the exported format and try again.', 'error')

    return redirect(url_for('main.personal_bests'))


@main.route('/personal-bests/<int:swim_id>/card')
@login_required
def pb_card(swim_id):
    from app import db
    from models import Swim
    from flask import abort

    swim = db.session.query(Swim).get(swim_id)
    if not swim or swim.user_id != current_user.id:
        abort(404)
    return render_template('pb_card.html', swim=swim)


@main.route('/goals', methods=['GET', 'POST'])
@login_required
def goals():
    from app import db
    from models import Goal, Swim

    if request.method == 'POST':
        event = request.form.get('event', '').strip()
        target_time = request.form.get('target_time', '').strip()
        pool = request.form.get('pool', '25m')
        target_date_raw = request.form.get('target_date') or ''
        notes = request.form.get('notes', '').strip()

        if not event or not target_time:
            flash('Pick an event and a target time.', 'error')
            return redirect(url_for('main.goals'))

        target_date_val = None
        if target_date_raw:
            try:
                target_date_val = datetime.strptime(target_date_raw, '%Y-%m-%d').date()
            except ValueError:
                flash('That target date is not valid.', 'error')
                return redirect(url_for('main.goals'))

        goal = Goal(
            user_id=current_user.id,
            event=event,
            pool=pool,
            target_time=target_time,
            target_date=target_date_val,
            notes=notes,
        )
        db.session.add(goal)
        db.session.commit()
        flash('Goal set.', 'success')
        return redirect(url_for('main.goals'))

    user_goals = (
        db.session.query(Goal)
        .filter_by(user_id=current_user.id)
        .order_by(Goal.created_at.desc())
        .all()
    )
    swims = db.session.query(Swim).filter_by(user_id=current_user.id).all()

    best_by_event = {}
    for s in swims:
        secs = s.time_in_seconds()
        if secs is None:
            continue
        current = best_by_event.get(s.event)
        if current is None or secs < current:
            best_by_event[s.event] = secs

    goal_rows = []
    for g in user_goals:
        best_secs = best_by_event.get(g.event)
        target_secs = g.target_seconds()
        achieved = best_secs is not None and target_secs is not None and best_secs <= target_secs
        gap = round(best_secs - target_secs, 2) if (best_secs is not None and target_secs is not None) else None
        goal_rows.append({'goal': g, 'best_secs': best_secs, 'achieved': achieved, 'gap': gap})

    return render_template('goals.html', goal_rows=goal_rows)


@main.route('/goals/<int:goal_id>/delete', methods=['POST'])
@login_required
def goals_delete(goal_id):
    from app import db
    from models import Goal

    g = db.session.query(Goal).get(goal_id)
    if g and g.user_id == current_user.id:
        db.session.delete(g)
        db.session.commit()
        flash('Goal removed.', 'success')
    return redirect(url_for('main.goals'))


from auth_utils import admin_required


def _log_admin_action(action, target_type=None, target_id=None, detail=None):
    from app import db
    from models import AdminAuditLog

    db.session.add(AdminAuditLog(
        admin_id=current_user.id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=detail,
    ))
    db.session.commit()


@main.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    from app import db
    from models import User, Swim, Session, SavedSet, Announcement, Club

    pending_clubs_count = db.session.query(Club).filter_by(status='pending').count()

    total_users = db.session.query(User).count()
    verified_users = db.session.query(User).filter_by(is_verified=True).count()
    unverified_users = total_users - verified_users
    total_swims = db.session.query(Swim).count()
    total_sessions = db.session.query(Session).count()

    q = request.args.get('q', '').strip().lower()
    plan_filter = request.args.get('plan', '')
    users_query = db.session.query(User).order_by(User.created_at.desc()).all()
    users = users_query
    if q:
        users = [u for u in users if q in u.username.lower() or q in u.email.lower()]
    if plan_filter:
        users = [u for u in users if u.plan == plan_filter]

    # --- signups per week, last 8 weeks, for the admin activity chart ---
    now = datetime.utcnow()
    week_start = now - timedelta(days=now.weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    weekly_signups = []
    for i in range(7, -1, -1):
        wk_start = week_start - timedelta(weeks=i)
        wk_end = wk_start + timedelta(days=7)
        weekly_signups.append(
            sum(1 for u in users_query if wk_start <= u.created_at < wk_end)
        )
    max_week_signups = max(weekly_signups) if any(weekly_signups) else 1

    site_announcement = (
        db.session.query(Announcement)
        .filter_by(squad_id=None)
        .order_by(Announcement.created_at.desc())
        .first()
    )

    return render_template(
        'admin_dashboard.html',
        total_users=total_users,
        verified_users=verified_users,
        unverified_users=unverified_users,
        total_swims=total_swims,
        total_sessions=total_sessions,
        users=users,
        q=q,
        plan_filter=plan_filter,
        weekly_signups=weekly_signups,
        max_week_signups=max_week_signups,
        site_announcement=site_announcement,
        pending_clubs_count=pending_clubs_count,
    )


@main.route('/admin/users/<int:user_id>/update', methods=['POST'])
@login_required
@admin_required
def admin_user_update(user_id):
    from app import db
    from models import User

    u = db.session.query(User).get(user_id)
    if not u:
        abort(404)

    new_plan = request.form.get('plan')
    new_role = request.form.get('role')
    changes = []
    if new_plan and new_plan != u.plan:
        changes.append(f"plan {u.plan} -> {new_plan}")
        u.plan = new_plan
    if new_role and new_role != u.role:
        changes.append(f"role {u.role} -> {new_role}")
        u.role = new_role

    if changes:
        db.session.commit()
        _log_admin_action('update_user', 'User', u.id, ', '.join(changes))
        flash(f'Updated {u.username}: {", ".join(changes)}', 'success')

    return redirect(url_for('main.admin_dashboard'))


@main.route('/admin/announcement', methods=['POST'])
@login_required
@admin_required
def admin_announcement_post():
    from app import db
    from models import Announcement

    message = request.form.get('message', '').strip()
    if message:
        db.session.add(Announcement(squad_id=None, author_id=current_user.id, message=message))
        db.session.commit()
        _log_admin_action('post_announcement', 'Announcement', None, message)
        flash('Announcement posted.', 'success')
    return redirect(url_for('main.admin_dashboard'))


@main.route('/admin/announcement/<int:ann_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_announcement_delete(ann_id):
    from app import db
    from models import Announcement

    a = db.session.query(Announcement).get(ann_id)
    if a and a.squad_id is None:
        db.session.delete(a)
        db.session.commit()
        _log_admin_action('clear_announcement', 'Announcement', ann_id)
        flash('Announcement cleared.', 'success')
    return redirect(url_for('main.admin_dashboard'))


@main.route('/admin/audit')
@login_required
@admin_required
def admin_audit():
    from app import db
    from models import AdminAuditLog, User

    logs = (
        db.session.query(AdminAuditLog)
        .order_by(AdminAuditLog.created_at.desc())
        .limit(200)
        .all()
    )
    admins = {u.id: u.username for u in db.session.query(User).all()}
    return render_template('admin_audit.html', logs=logs, admins=admins)


@main.route('/admin/clubs')
@login_required
@admin_required
def admin_clubs():
    from app import db
    from models import Club, User

    clubs = db.session.query(Club).order_by(Club.created_at.desc()).all()
    owners = {u.id: u.username for u in db.session.query(User).all()}
    return render_template('admin_clubs.html', clubs=clubs, owners=owners)


@main.route('/admin/clubs/<int:club_id>/approve', methods=['POST'])
@login_required
@admin_required
def admin_clubs_approve(club_id):
    from app import db
    from models import Club

    club = db.session.query(Club).get(club_id)
    if club:
        club.status = 'active'
        club.approved_at = datetime.utcnow()
        db.session.commit()
        _log_admin_action('approve_club', 'Club', club.id, club.name)
        flash(f'"{club.name}" approved.', 'success')
    return redirect(url_for('main.admin_clubs'))


@main.route('/admin/clubs/<int:club_id>/reject', methods=['POST'])
@login_required
@admin_required
def admin_clubs_reject(club_id):
    from app import db
    from models import Club

    club = db.session.query(Club).get(club_id)
    if club:
        name = club.name
        db.session.delete(club)
        db.session.commit()
        _log_admin_action('reject_club', 'Club', club_id, name)
        flash(f'"{name}" rejected and removed.', 'success')
    return redirect(url_for('main.admin_clubs'))


@main.route('/admin/standards')
@login_required
@admin_required
def admin_standards():
    from app import db
    from models import Standard

    standards = db.session.query(Standard).order_by(Standard.event, Standard.name).all()
    return render_template('admin_standards.html', standards=standards)


@main.route('/admin/standards/create', methods=['POST'])
@login_required
@admin_required
def admin_standards_create():
    from app import db
    from models import Standard

    name = request.form.get('name', '').strip()
    event = request.form.get('event', '').strip()
    cutoff_time = request.form.get('cutoff_time', '').strip()

    if not name or not event or not cutoff_time:
        flash('Name, event and cutoff time are required.', 'error')
        return redirect(url_for('main.admin_standards'))

    standard = Standard(
        name=name,
        event=event,
        pool=request.form.get('pool', '25m'),
        gender=request.form.get('gender', 'open'),
        age_group=request.form.get('age_group', '').strip(),
        cutoff_time=cutoff_time,
    )
    db.session.add(standard)
    db.session.commit()
    _log_admin_action('create_standard', 'Standard', standard.id, name)
    flash('Standard added.', 'success')
    return redirect(url_for('main.admin_standards'))


@main.route('/admin/standards/delete/<int:standard_id>', methods=['POST'])
@login_required
@admin_required
def admin_standards_delete(standard_id):
    from app import db
    from models import Standard

    s = db.session.query(Standard).get(standard_id)
    if s:
        db.session.delete(s)
        db.session.commit()
        _log_admin_action('delete_standard', 'Standard', standard_id, s.name)
        flash('Standard removed.', 'success')
    return redirect(url_for('main.admin_standards'))

@main.route('/admin/programs')
@login_required
@admin_required
def admin_programs():
    from app import db
    from models import TrainingProgram

    programs = db.session.query(TrainingProgram).order_by(TrainingProgram.created_at.desc()).all()
    return render_template('admin_programs.html', programs=programs)


@main.route('/admin/programs/create', methods=['POST'])
@login_required
@admin_required
def admin_programs_create():
    from app import db
    from models import TrainingProgram

    title = request.form.get('title', '').strip()
    category = request.form.get('category', 'Strength')
    description = request.form.get('description', '').strip()
    content_blocks = request.form.get('content_blocks', '[]')

    if not title:
        flash('Program needs a title.', 'error')
        return redirect(url_for('main.admin_programs'))

    program = TrainingProgram(
        title=title,
        category=category,
        description=description,
        content_blocks=content_blocks,
        created_by=current_user.id,
    )
    db.session.add(program)
    db.session.commit()
    _log_admin_action('create_program', 'TrainingProgram', program.id, title)
    flash('Program created.', 'success')
    return redirect(url_for('main.admin_programs'))


@main.route('/admin/programs/delete/<int:program_id>', methods=['POST'])
@login_required
@admin_required
def admin_programs_delete(program_id):
    from app import db
    from models import TrainingProgram

    p = db.session.query(TrainingProgram).get(program_id)
    if p:
        db.session.delete(p)
        db.session.commit()
        _log_admin_action('delete_program', 'TrainingProgram', program_id, p.title)
        flash('Program deleted.', 'success')
    return redirect(url_for('main.admin_programs'))


@main.route('/admin/sets')
@login_required
@admin_required
def admin_sets():
    from app import db
    from models import SavedSet

    sets = db.session.query(SavedSet).order_by(SavedSet.created_at.desc()).all()
    return render_template('admin_sets.html', sets=sets, categories=SET_CATEGORIES)

@main.route('/admin/sets/create', methods=['POST'])
@login_required
@admin_required
def admin_sets_create():
    from app import db
    from models import SavedSet

    name = request.form.get('name', '').strip()
    pool = request.form.get('pool', '25m')
    session_type = request.form.get('session_type', 'Training')
    sets_data = request.form.get('sets_data', '[]')
    category = request.form.get('category', 'Fitness')
    description = request.form.get('description', '').strip()

    if not name:
        flash('Set needs a name.', 'error')
        return redirect(url_for('main.admin_sets'))

    new_set = SavedSet(
        name=name,
        pool=pool,
        session_type=session_type,
        sets_data=sets_data,
        category=category,
        description=description,
        created_by=current_user.id
    )
    db.session.add(new_set)
    db.session.commit()
    flash('Set created.', 'success')
    return redirect(url_for('main.admin_sets'))

@main.route('/admin/sets/delete/<int:set_id>', methods=['POST'])
@login_required
@admin_required
def admin_sets_delete(set_id):
    from app import db
    from models import SavedSet

    s = db.session.query(SavedSet).get(set_id)
    if s:
        db.session.delete(s)
        db.session.commit()
        _log_admin_action('delete_set', 'SavedSet', set_id, s.name)
        flash('Set deleted.', 'success')
    return redirect(url_for('main.admin_sets'))