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
    'IM': 'IM', 'Kick': 'Kick', 'Pull': 'Pull', 'Drill': 'Drill', 'Snorkel': 'Snorkel',
}

DIFFICULTIES = ['Easy', 'Medium', 'Hard', 'Technical']
DISTANCE_FOCUS = ['Short', 'Middle', 'Long', 'All']


def _group_rounds(blocks):
    """Collapse a run of consecutive blocks sharing the same round_reps > 1
    (a whiteboard bracket like '2x{ 4x75 / 8x50 / 2x25 }') into one 'round'
    row, so the template can show a single '×N rounds' badge beside the whole
    group instead of repeating it inside every block. Ungrouped blocks
    (round_reps absent or 1) pass through as their own row."""
    rows = []
    i, n = 0, len(blocks)
    while i < n:
        rr = int(blocks[i].get('round_reps') or 1)
        if rr > 1:
            group = []
            while i < n and int(blocks[i].get('round_reps') or 1) == rr:
                group.append(blocks[i])
                i += 1
            rows.append({'kind': 'round', 'round_reps': rr, 'blocks': group})
        else:
            rows.append({'kind': 'single', 'block': blocks[i]})
            i += 1
    return rows

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
        # Never assume the fields are present -- a crafted POST can omit any of
        # them, and .strip() on None would 500. Default to '' and validate.
        username = (request.form.get('username') or '').strip()
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''

        if not (3 <= len(username) <= 30):
            flash('Username must be between 3 and 30 characters.', 'error')
            return redirect(url_for('main.signup'))
        if not re.match(r'^[A-Za-z0-9 ._-]+$', username):
            flash('Username can only use letters, numbers, spaces, and . _ -', 'error')
            return redirect(url_for('main.signup'))

        if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email) or len(email) > 150:
            flash('Please enter a valid email address.', 'error')
            return redirect(url_for('main.signup'))

        if not (8 <= len(password) <= 200):
            flash('Password must be between 8 and 200 characters.', 'error')
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

        if not send_verification_email(email, username, code):
            flash(
                "Your account was created, but we couldn't send the verification email "
                "right now. Try 'Resend code' on the next screen in a moment, or contact us.",
                'error',
            )
        return redirect(url_for('main.verify', email=email))

    return render_template('signup.html')

@main.route('/verify', methods=['GET', 'POST'])
def verify():
    from app import db
    from models import User

    email = request.args.get('email') or request.form.get('email')
    user = db.session.query(User).filter_by(email=email).first()

    if not user:
        flash("We couldn't find that account. Please sign up again.", 'error')
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

        if (user.verify_attempts or 0) >= 5:
            flash('Too many incorrect attempts. Request a new code to try again.', 'error')
            return render_template('verify.html', email=email)

        if code == user.verify_code:
            user.is_verified = True
            user.verify_code = None
            user.verify_attempts = 0
            db.session.commit()
            login_user(user)
            flash('Email verified. Welcome to STROKE!', 'success')
            return redirect(url_for('main.dashboard'))
        else:
            user.verify_attempts = (user.verify_attempts or 0) + 1
            db.session.commit()
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
        if send_verification_email(email, user.username, code):
            flash('New code sent.', 'success')
        else:
            flash("Couldn't send the email right now — try again in a moment.", 'error')

    return redirect(url_for('main.verify', email=email))

@main.route('/login', methods=['GET', 'POST'])
def login():
    from app import db
    from models import User

    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''
        user = db.session.query(User).filter_by(email=email).first()

        if not user:
            flash('Incorrect email or password.', 'error')
            return redirect(url_for('main.login'))

        if user.login_locked_until and datetime.utcnow() < user.login_locked_until:
            flash('Too many failed attempts. Try again in a few minutes.', 'error')
            return redirect(url_for('main.login'))

        if user.check_password(password):
            user.failed_login_attempts = 0
            user.login_locked_until = None
            db.session.commit()

            if not user.is_verified:
                flash('Please verify your email first.', 'error')
                return redirect(url_for('main.verify', email=email))
            remember = bool(request.form.get('remember'))
            login_user(user, remember=remember)
            if user.is_admin:
                return redirect(url_for('main.admin_dashboard'))
            if user.role == 'coach':
                return redirect(url_for('coach.coach_dashboard'))
            return redirect(url_for('main.dashboard'))
        else:
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
            if user.failed_login_attempts >= 5:
                user.login_locked_until = datetime.utcnow() + timedelta(minutes=15)
            db.session.commit()
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
    if user.role == 'coach':
        return redirect(url_for('coach.coach_dashboard'))
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

    # Coaches live on the coach side — keep coach accounts there (admins keep full access).
    if current_user.role == 'coach' and not current_user.is_admin:
        return redirect(url_for('coach.coach_dashboard'))

    needs_ai_onboarding = False
    todays_program = None
    checkin_prompt = None
    if current_user.is_solo:
        solo_profile = db.session.query(AthleteProfile).filter_by(user_id=current_user.id).first()
        needs_ai_onboarding = solo_profile is None
        # Gentle AI coach check-in: due every 3-4 days, never daily nagging.
        if solo_profile:
            import athlete_model
            nudge = athlete_model.checkin_nudge(current_user.id)
            if nudge['due']:
                checkin_prompt = nudge
        # Today's session from the AI program, matched to the weekday.
        if solo_profile and solo_profile.program_json:
            program = solo_profile.get_program()
            today_name = datetime.utcnow().strftime('%A')
            todays_program = next(
                (d for d in program.get('days', []) if d.get('day') == today_name), None
            )

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
        checkin_prompt=checkin_prompt,
        todays_program=todays_program,
        todays_program_weekday=datetime.utcnow().strftime('%A'),
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
        from validation import clean_time, clean_text, clean_splits, clean_sets_json
        import athlete_model

        log_type = request.form.get('log_type')
        notes = clean_text(request.form.get('notes'), 2000)
        pool = request.form.get('pool') if request.form.get('pool') in ('25m', '50m') else '25m'

        if log_type == 'pb':
            # Save a PB / race time. The time must actually parse as a swim
            # time -- '1e100', 'Infinity' or a 40-digit number never reach the DB.
            event = clean_text(request.form.get('event'), 50)
            time_norm, _secs = clean_time(request.form.get('time'), key='swim_seconds')
            if not event:
                flash('Pick an event first.', 'error')
                return redirect(url_for('main.log'))
            if time_norm is None:
                flash("That time doesn't look right — enter it like 1:02.50 or 58.90.", 'error')
                return redirect(url_for('main.log'))

            splits_raw = request.form.get('splits', '[]')
            try:
                splits_list = json.loads(splits_raw)
            except ValueError:
                splits_list = []
            splits_list = clean_splits(splits_list)

            swim = Swim(
                user_id=current_user.id,
                event=event,
                pool=pool,
                stroke=clean_text(request.form.get('stroke'), 10),
                time=time_norm,
                notes=notes,
                tag=request.form.get('tag') if request.form.get('tag') in ('practice', 'meet') else 'practice',
                splits=json.dumps(splits_list) if splits_list else None,
                logged_at=datetime.utcnow()
            )
            db.session.add(swim)
            db.session.commit()
            athlete_model.update_athlete_state(current_user.id)
            flash('PB logged!', 'success')

        elif log_type == 'session':
            # Save a full training session. Blocks are validated server-side:
            # bad reps/distances/rests are cleaned or dropped, never stored.
            sets_json, blocks = clean_sets_json(request.form.get('session_data', '[]'))
            if not blocks:
                flash('That session had no valid sets — check the reps and distances.', 'error')
                return redirect(url_for('main.log'))
            session = Session(
                user_id=current_user.id,
                session_type=clean_text(request.form.get('event'), 50),
                pool=pool,
                sets_data=sets_json,
                notes=notes,
                logged_at=datetime.utcnow()
            )
            db.session.add(session)
            db.session.commit()
            athlete_model.update_athlete_state(current_user.id)
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


def _library_sets_query(db):
    """Public Set Library only shows admin-curated sets, not other users'
    private (e.g. coach AI-generated) SavedSet rows."""
    from models import SavedSet, User
    admin_ids = [u.id for u in db.session.query(User.id).filter_by(is_admin=True).all()]
    return db.session.query(SavedSet).filter(SavedSet.created_by.in_(admin_ids))


@main.route('/sets')
@login_required
def sets_library():
    from app import db

    saved_sets = _library_sets_query(db).all()
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

    all_sets = (
        _library_sets_query(db)
        .filter(SavedSet.category == category['key'])
        .order_by(SavedSet.created_at.desc())
        .all()
    )

    difficulty = request.args.get('difficulty') or ''
    distance = request.args.get('distance') or ''
    sets = all_sets
    if difficulty in DIFFICULTIES:
        sets = [s for s in sets if (s.difficulty or 'Medium') == difficulty]
    if distance in DISTANCE_FOCUS:
        sets = [s for s in sets if (s.distance_focus or 'All') in (distance, 'All')]

    return render_template(
        'sets_category.html', category=category, sets=sets[:50], total_count=len(all_sets),
        difficulties=DIFFICULTIES, distances=DISTANCE_FOCUS,
        active_difficulty=difficulty, active_distance=distance,
    )


@main.route('/sets/view/<int:set_id>')
@login_required
def sets_view(set_id):
    import json
    from app import db
    from models import SavedSet
    from flask import abort

    s = _library_sets_query(db).filter(SavedSet.id == set_id).first()
    if not s:
        abort(404)

    category = _find_category(key=(s.category or 'Fitness')) or SET_CATEGORIES[5]
    try:
        blocks = json.loads(s.sets_data or '[]')
    except ValueError:
        blocks = []

    # Older sets stored before rest_type existed don't have it -- fall back to
    # the same physically-grounded guess used everywhere else: a send-off
    # can never be shorter than the swim it times, so a too-short rest can
    # only be a literal rest gap, not an interval.
    from swim_logic import parse_time as _parse_time, estimate_rep_seconds, infer_rest_type
    for b in blocks:
        if b.get('rest_type') not in ('interval', 'rest'):
            reps = int(b.get('reps') or 0)
            est_swim = estimate_rep_seconds(b.get('dist'), b.get('stroke'), b.get('modifier'))
            b['rest_type'] = infer_rest_type(reps, _parse_time(b.get('rest')), est_swim, b.get('note'))

    # Group blocks into workout sections in canonical order. Older sets
    # without a section field all land in "Main set".
    section_order = ['Warm up', 'Pre set', 'Main set', 'Sub set', 'Cool down']
    sections = []
    for name in section_order:
        sec_blocks = [b for b in blocks if b.get('section', 'Main set') == name]
        if sec_blocks:
            dist = sum(
                (int(b.get('reps', 0) or 0)) * (int(b.get('dist', 0) or 0)) * int(b.get('round_reps') or 1)
                for b in sec_blocks
            )
            sections.append({'name': name, 'blocks': sec_blocks, 'rows': _group_rounds(sec_blocks), 'distance': dist})

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

    from validation import clean_sets_json, clean_text

    name = clean_text(request.form.get('name'), 100)
    pool = request.form.get('pool') if request.form.get('pool') in ('25m', '50m') else '25m'
    session_type = clean_text(request.form.get('session_type'), 50) or 'Training'
    sets_data, blocks = clean_sets_json(request.form.get('sets_data', '[]'))
    category = request.form.get('category', 'Fitness')
    difficulty = request.form.get('difficulty') if request.form.get('difficulty') in DIFFICULTIES else 'Medium'
    distance_focus = request.form.get('distance_focus') if request.form.get('distance_focus') in DISTANCE_FOCUS else 'All'
    description = clean_text(request.form.get('description'), 2000)

    if not name:
        return {'ok': False, 'error': 'Set needs a name.'}, 400
    if not blocks:
        return {'ok': False, 'error': 'That set has no valid blocks — check the reps and distances.'}, 400

    new_set = SavedSet(
        name=name,
        pool=pool,
        session_type=session_type,
        sets_data=sets_data,
        category=category,
        difficulty=difficulty,
        distance_focus=distance_focus,
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

    from models import AthleteProfile
    progress_profile = db.session.query(AthleteProfile).filter_by(user_id=current_user.id).first()
    analysis_wait_hours = None
    if progress_profile and progress_profile.progress_insight_at:
        elapsed = datetime.utcnow() - progress_profile.progress_insight_at
        if elapsed < timedelta(hours=24):
            analysis_wait_hours = round((timedelta(hours=24) - elapsed).total_seconds() / 3600, 1)

    return render_template(
        'personal_bests.html',
        pb_rows=pb_rows,
        swims=filtered,
        q=request.args.get('q', ''),
        pool_filter=pool_filter,
        tag_filter=tag_filter,
        trend_rows=trend_rows,
        prediction_rows=prediction_rows,
        progress_profile=progress_profile,
        analysis_wait_hours=analysis_wait_hours,
    )


def _build_progression_digest(user_id):
    """Deterministic per-swimmer progression profile: rolling-window time
    trends, PB recency, training load, squad attendance and check-in
    correlation. Returns (has_data, digest_text) -- digest_text is plain
    text meant to be handed to ai_utils.generate_progress_insight, not
    rendered directly. All numbers here are plain math, no AI."""
    from app import db
    from models import Swim, Session, CheckIn, AttendanceRecord
    import statistics

    now = datetime.utcnow()
    cutoff_recent = now - timedelta(weeks=8)
    cutoff_prior = now - timedelta(weeks=16)

    def _fmt_secs(secs):
        if secs >= 60:
            return f'{int(secs // 60)}:{secs % 60:05.2f}'
        return f'{secs:.2f}'

    swims = db.session.query(Swim).filter_by(user_id=user_id).order_by(Swim.logged_at.asc()).all()

    by_event = {}
    for s in swims:
        secs = s.time_in_seconds()
        if secs is not None:
            by_event.setdefault(s.event, []).append((s.logged_at, secs))

    trend_lines = []
    for event, entries in by_event.items():
        recent = [secs for dt, secs in entries if dt >= cutoff_recent]
        prior = [secs for dt, secs in entries if cutoff_prior <= dt < cutoff_recent]
        window_note = ""
        if len(recent) < 2 or len(prior) < 2:
            # Not enough calendar spread yet (new accounts, or history under 16
            # weeks) -- fall back to a plain count-based split, same approach as
            # the on-page Training trends table, so newer swimmers still get a
            # read rather than "not enough data" for months.
            times_only = [secs for _, secs in entries]
            if len(times_only) < 4:
                continue
            half = len(times_only) // 2
            prior, recent = times_only[:half], times_only[half:]
            window_note = ", count-based split (not enough calendar spread yet for the 8-week window)"
        recent_avg = sum(recent) / len(recent)
        prior_avg = sum(prior) / len(prior)
        change_pct = (recent_avg - prior_avg) / prior_avg * 100
        direction = 'improving' if change_pct < -0.4 else 'slipping' if change_pct > 0.4 else 'steady'
        consistency = statistics.pstdev(recent) if len(recent) > 1 else 0.0
        trend_lines.append(
            f"{event}: {direction} ({abs(round(change_pct, 1))}% vs prior period{window_note}), "
            f"recent avg {_fmt_secs(recent_avg)} (n={len(recent)}), consistency ±{consistency:.2f}s"
        )

    best_by_event = {}
    for s in swims:
        secs = s.time_in_seconds()
        if secs is None:
            continue
        cur = best_by_event.get(s.event)
        if cur is None or secs < cur[1]:
            best_by_event[s.event] = (s.logged_at, secs)
    pb_lines = [
        f"{event}: PB {_fmt_secs(secs)} set {(now - dt).days}d ago"
        for event, (dt, secs) in best_by_event.items()
    ]

    sessions = db.session.query(Session).filter_by(user_id=user_id).all()
    recent_sessions = [s for s in sessions if s.logged_at >= cutoff_recent]
    prior_sessions = [s for s in sessions if cutoff_prior <= s.logged_at < cutoff_recent]
    load_line = (
        f"Training load: {len(recent_sessions)} sessions / {sum(s.total_distance() for s in recent_sessions)}m "
        f"in the last 8 weeks vs {len(prior_sessions)} sessions / {sum(s.total_distance() for s in prior_sessions)}m "
        f"the 8 weeks before that."
    )

    attendance_recent = (
        db.session.query(AttendanceRecord)
        .filter(AttendanceRecord.swimmer_id == user_id, AttendanceRecord.session_date >= cutoff_recent.date())
        .all()
    )
    attendance_line = None
    if attendance_recent:
        present = sum(1 for a in attendance_recent if a.status in ('present', 'late'))
        attendance_line = f"Squad attendance: {present}/{len(attendance_recent)} marked sessions in last 8 weeks."

    checkins = (
        db.session.query(CheckIn)
        .filter(CheckIn.user_id == user_id, CheckIn.checkin_date >= cutoff_recent.date())
        .all()
    )
    checkin_line = None
    if checkins:
        feelings = [c.feeling_rating for c in checkins if c.feeling_rating]
        fatigues = [c.fatigue_rating for c in checkins if c.fatigue_rating]
        sleeps = [c.sleep_quality for c in checkins if c.sleep_quality]
        parts = []
        if feelings:
            parts.append(f"avg feeling {sum(feelings) / len(feelings):.1f}/5")
        if fatigues:
            parts.append(f"avg fatigue {sum(fatigues) / len(fatigues):.1f}/5")
        if sleeps:
            parts.append(f"avg sleep {sum(sleeps) / len(sleeps):.1f}/5")
        if parts:
            checkin_line = f"Check-ins (last 8 weeks, n={len(checkins)}): " + ", ".join(parts)

    lines = []
    if trend_lines:
        lines.append("Per-event time trends:\n" + "\n".join(f"- {l}" for l in trend_lines))
    if pb_lines:
        lines.append("PB recency:\n" + "\n".join(f"- {l}" for l in pb_lines))
    lines.append(load_line)
    if attendance_line:
        lines.append(attendance_line)
    if checkin_line:
        lines.append(checkin_line)

    has_data = bool(trend_lines)
    return has_data, "\n\n".join(lines)


@main.route('/personal-bests/analyze', methods=['POST'])
@login_required
def personal_bests_analyze():
    from flask import current_app
    from app import db
    from models import AthleteProfile
    from ai_utils import generate_progress_insight

    if not current_app.config.get('ANTHROPIC_API_KEY'):
        flash("AI analysis isn't set up yet.", 'error')
        return redirect(url_for('main.personal_bests'))

    profile = db.session.query(AthleteProfile).filter_by(user_id=current_user.id).first()
    if profile and profile.progress_insight_at and datetime.utcnow() - profile.progress_insight_at < timedelta(hours=24):
        flash("You've already got a fresh analysis — check back later for an update.", 'error')
        return redirect(url_for('main.personal_bests'))

    has_data, digest = _build_progression_digest(current_user.id)
    if not has_data:
        flash("Not enough repeated timed swims yet — log a few more of the same event to unlock an AI analysis.", 'error')
        return redirect(url_for('main.personal_bests'))

    tone = profile.coaching_tone if profile else 'encouraging'
    result = generate_progress_insight(
        digest, current_app.config['ANTHROPIC_API_KEY'], current_app.config['ANTHROPIC_MODEL'], tone=tone,
    )
    if not result.get('ok'):
        flash(result.get('error', "Couldn't generate an analysis — try again."), 'error')
        return redirect(url_for('main.personal_bests'))

    if not profile:
        profile = AthleteProfile(user_id=current_user.id)
        db.session.add(profile)
    profile.progress_insight = json.dumps(result['insight'])
    profile.progress_insight_at = datetime.utcnow()
    db.session.commit()
    flash('Your progression analysis is ready.', 'success')
    return redirect(url_for('main.personal_bests'))


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
        from validation import clean_time, clean_text, clean_splits
        import athlete_model

        MAX_IMPORT_ROWS = 2000
        for row in reader:
            if count >= MAX_IMPORT_ROWS:
                break
            event = clean_text(row.get('event'), 50)
            time_norm, _secs = clean_time(row.get('time'), key='swim_seconds')
            if not event or time_norm is None:
                continue  # skip junk rows rather than poisoning the log
            splits_raw = (row.get('splits') or '').strip()
            splits_list = clean_splits([x.strip() for x in splits_raw.split(';') if x.strip()]) if splits_raw else []
            swim = Swim(
                user_id=current_user.id,
                event=event,
                pool=(row.get('pool') or '').strip() if (row.get('pool') or '').strip() in ('25m', '50m') else '25m',
                stroke=clean_text(row.get('stroke'), 10),
                time=time_norm,
                tag=(row.get('tag') or '').strip() if (row.get('tag') or '').strip() in ('practice', 'meet') else 'practice',
                splits=json.dumps(splits_list) if splits_list else None,
                notes=clean_text(row.get('notes'), 2000),
            )
            db.session.add(swim)
            count += 1
        db.session.commit()
        if count:
            athlete_model.update_athlete_state(current_user.id)
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
        from validation import clean_time, clean_text

        event = clean_text(request.form.get('event'), 50)
        target_time_raw = (request.form.get('target_time') or '').strip()
        pool = request.form.get('pool') if request.form.get('pool') in ('25m', '50m') else '25m'
        target_date_raw = request.form.get('target_date') or ''
        notes = clean_text(request.form.get('notes'), 2000)

        if not event or not target_time_raw:
            flash('Pick an event and a target time.', 'error')
            return redirect(url_for('main.goals'))

        target_time, _secs = clean_time(target_time_raw, key='goal_seconds')
        if target_time is None:
            flash("That target time doesn't look right — enter it like 1:02.50 or 58.90.", 'error')
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
    role_filter = request.args.get('role', '')
    users_query = db.session.query(User).order_by(User.created_at.desc()).all()
    users = users_query
    if q:
        users = [u for u in users if q in u.username.lower() or q in u.email.lower()]
    if plan_filter:
        users = [u for u in users if u.plan == plan_filter]
    if role_filter:
        users = [u for u in users if u.role == role_filter]

    total_coaches = sum(1 for u in users_query if u.role == 'coach')

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
        role_filter=role_filter,
        total_coaches=total_coaches,
        weekly_signups=weekly_signups,
        max_week_signups=max_week_signups,
        site_announcement=site_announcement,
        pending_clubs_count=pending_clubs_count,
    )


@main.route('/admin/solo')
@login_required
@admin_required
def admin_solo():
    from app import db
    from models import User

    q = request.args.get('q', '').strip().lower()
    paid_filter = request.args.get('paid', '')

    users = (
        db.session.query(User)
        .filter(User.plan.in_(['solo', 'solo_pro']))
        .order_by(User.created_at.desc())
        .all()
    )
    if q:
        users = [u for u in users if q in u.username.lower() or q in u.email.lower()]
    if paid_filter == 'yes':
        users = [u for u in users if u.solo_paid]
    elif paid_filter == 'no':
        users = [u for u in users if not u.solo_paid]

    all_solo = (
        db.session.query(User).filter(User.plan.in_(['solo', 'solo_pro'])).all()
    )
    paid_count = sum(1 for u in all_solo if u.solo_paid)

    return render_template(
        'admin_solo.html',
        users=users, q=q, paid_filter=paid_filter,
        total_solo=len(all_solo), paid_count=paid_count,
    )


@main.route('/admin/solo/<int:user_id>')
@login_required
@admin_required
def admin_solo_detail(user_id):
    from app import db
    from models import User, AthleteProfile, CoachMessage, InjuryStatus, DrylandLogEntry

    u = db.session.query(User).get(user_id)
    if not u:
        abort(404)

    profile = db.session.query(AthleteProfile).filter_by(user_id=user_id).first()
    injury = db.session.query(InjuryStatus).filter_by(user_id=user_id).first()
    dryland_entries = (
        db.session.query(DrylandLogEntry)
        .filter_by(user_id=user_id)
        .order_by(DrylandLogEntry.logged_at.desc())
        .limit(10)
        .all()
    )
    nutrition_msg_count = db.session.query(CoachMessage).filter_by(user_id=user_id, topic='nutrition').count()
    dryland_msg_count = db.session.query(CoachMessage).filter_by(user_id=user_id, topic='dryland').count()
    last_coach_message = (
        db.session.query(CoachMessage)
        .filter_by(user_id=user_id)
        .order_by(CoachMessage.created_at.desc())
        .first()
    )

    return render_template(
        'admin_solo_detail.html',
        u=u, profile=profile, injury=injury, dryland_entries=dryland_entries,
        nutrition_msg_count=nutrition_msg_count, dryland_msg_count=dryland_msg_count,
        last_coach_message=last_coach_message,
        program=profile.get_program() if profile else {},
        nutrition=profile.get_nutrition() if profile else {},
        dryland=profile.get_dryland() if profile else {},
    )


@main.route('/admin/solo/<int:user_id>/paid', methods=['POST'])
@login_required
@admin_required
def admin_solo_toggle_paid(user_id):
    from app import db
    from models import User

    u = db.session.query(User).get(user_id)
    if not u:
        abort(404)

    u.solo_paid = not u.solo_paid
    u.solo_paid_at = datetime.utcnow() if u.solo_paid else None
    db.session.commit()
    _log_admin_action('toggle_solo_paid', 'User', u.id, f"solo_paid -> {u.solo_paid}")
    flash(f"{u.username} marked as {'paid' if u.solo_paid else 'unpaid'}.", 'success')

    next_url = request.form.get('next', '')
    if next_url.startswith('/admin/solo'):
        return redirect(next_url)
    return redirect(url_for('main.admin_solo'))


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
        if new_plan not in ('free', 'solo', 'solo_pro', 'coach'):
            flash('Invalid plan value.', 'error')
            return redirect(url_for('main.admin_dashboard'))
        changes.append(f"plan {u.plan} -> {new_plan}")
        u.plan = new_plan
    if new_role and new_role != u.role:
        if new_role not in ('swimmer', 'coach'):
            flash('Invalid role value.', 'error')
            return redirect(url_for('main.admin_dashboard'))
        changes.append(f"role {u.role} -> {new_role}")
        u.role = new_role

    if changes:
        db.session.commit()
        _log_admin_action('update_user', 'User', u.id, ', '.join(changes))
        flash(f'Updated {u.username}: {", ".join(changes)}', 'success')

    return redirect(url_for('main.admin_dashboard'))


@main.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_user_delete(user_id):
    from app import db
    from models import User

    u = db.session.query(User).get(user_id)
    if not u:
        abort(404)
    if u.id == current_user.id:
        flash("You can't delete your own account.", 'error')
        return redirect(url_for('main.admin_dashboard'))

    username, email = u.username, u.email
    try:
        db.session.delete(u)
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash(f"Couldn't delete {username} — they still have linked data (swims, sets, etc).", 'error')
        return redirect(url_for('main.admin_dashboard'))

    _log_admin_action('delete_user', 'User', user_id, f'{username} <{email}>')
    flash(f'Deleted {username}.', 'success')
    return redirect(url_for('main.admin_dashboard'))


@main.route('/admin/users/<int:user_id>/resend-verification', methods=['POST'])
@login_required
@admin_required
def admin_user_resend_verification(user_id):
    from app import db
    from models import User
    from email_utils import send_verification_email

    u = db.session.query(User).get(user_id)
    if not u:
        abort(404)
    if u.is_verified:
        flash(f'{u.username} is already verified.', 'error')
        return redirect(url_for('main.admin_dashboard'))

    code = u.generate_verify_code()
    db.session.commit()
    if send_verification_email(u.email, u.username, code):
        _log_admin_action('resend_verification', 'User', u.id, u.email)
        flash(f'Verification email resent to {u.email}.', 'success')
    else:
        flash("Couldn't send the email right now — try again in a moment.", 'error')
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

    from validation import clean_time, clean_text

    name = clean_text(request.form.get('name'), 100)
    event = clean_text(request.form.get('event'), 50)
    cutoff_raw = (request.form.get('cutoff_time') or '').strip()

    if not name or not event or not cutoff_raw:
        flash('Name, event and cutoff time are required.', 'error')
        return redirect(url_for('main.admin_standards'))

    cutoff_time, _secs = clean_time(cutoff_raw, key='goal_seconds')
    if cutoff_time is None:
        flash("That cutoff time doesn't look right — enter it like 1:02.50 or 58.90.", 'error')
        return redirect(url_for('main.admin_standards'))

    standard = Standard(
        name=name,
        event=event,
        pool=request.form.get('pool') if request.form.get('pool') in ('25m', '50m') else '25m',
        gender=request.form.get('gender') if request.form.get('gender') in ('men', 'women', 'open') else 'open',
        age_group=clean_text(request.form.get('age_group'), 30),
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

    from validation import clean_sets_json, clean_text

    name = clean_text(request.form.get('name'), 100)
    pool = request.form.get('pool') if request.form.get('pool') in ('25m', '50m') else '25m'
    session_type = clean_text(request.form.get('session_type'), 50) or 'Training'
    sets_data, blocks = clean_sets_json(request.form.get('sets_data', '[]'))
    category = request.form.get('category', 'Fitness')
    difficulty = request.form.get('difficulty') if request.form.get('difficulty') in DIFFICULTIES else 'Medium'
    distance_focus = request.form.get('distance_focus') if request.form.get('distance_focus') in DISTANCE_FOCUS else 'All'
    description = clean_text(request.form.get('description'), 2000)

    if not name:
        flash('Set needs a name.', 'error')
        return redirect(url_for('main.admin_sets'))
    if not blocks:
        flash('That set has no valid blocks — check the reps and distances.', 'error')
        return redirect(url_for('main.admin_sets'))

    new_set = SavedSet(
        name=name,
        pool=pool,
        session_type=session_type,
        sets_data=sets_data,
        category=category,
        difficulty=difficulty,
        distance_focus=distance_focus,
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