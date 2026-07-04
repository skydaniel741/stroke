from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime, timedelta

main = Blueprint('main', __name__)

@main.route('/')
def home():
    return render_template('index.html')

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

@main.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.home'))

@main.route('/dashboard')
@login_required
def dashboard():
    from app import db
    from models import Swim, Session
    from datetime import timedelta

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

    # --- last 8 weeks volume, for the bar chart ---
    weekly_volume = []
    for i in range(7, -1, -1):
        wk_start = week_start - timedelta(weeks=i)
        wk_end = wk_start + timedelta(days=7)
        wk_total = (
            sum(s.total_distance() for s in sessions if wk_start <= s.logged_at < wk_end) +
            sum(s.distance() for s in swims if wk_start <= s.logged_at < wk_end)
        )
        weekly_volume.append(wk_total)

    max_week = max(weekly_volume) if any(weekly_volume) else 1

    # --- recent activity feed: swims + sessions, merged and sorted ---
    recent_activity = sorted(
        [
            {
                'kind': 'PB',
                'label': s.event,
                'pool': s.pool or '—',
                'logged_at': s.logged_at,
            } for s in swims
        ] + [
            {
                'kind': s.session_type or 'Session',
                'label': f"{len(s.get_sets())} set" + ('s' if len(s.get_sets()) != 1 else '') if s.get_sets() else (s.session_type or 'Session'),
                'pool': s.pool or '—',
                'logged_at': s.logged_at,
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

    return render_template(
        'dashboard.html',
        swims=swims,
        sessions=sessions,
        sessions_this_week=sessions_logged_count,
        volume_this_week=volume_this_week,
        streak=streak,
        weekly_volume=weekly_volume,
        max_week=max_week,
        recent_activity=recent_activity,
        personal_bests=personal_bests,
        streak_days=streak_days
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
            swim = Swim(
                user_id=current_user.id,
                event=request.form.get('event'),
                pool=request.form.get('pool'),
                stroke=request.form.get('stroke'),
                time=request.form.get('time'),
                notes=notes,
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

    saved_sets = db.session.query(SavedSet).order_by(SavedSet.created_at.desc()).all()
    last_session = (
        db.session.query(Session)
        .filter_by(user_id=current_user.id)
        .order_by(Session.logged_at.desc())
        .first()
    )
    return render_template('log.html', saved_sets=saved_sets, last_session=last_session)


@main.route('/sets/create', methods=['POST'])
@login_required
def sets_create():
    from app import db
    from models import SavedSet

    name = (request.form.get('name') or '').strip()
    pool = request.form.get('pool', '25m')
    session_type = request.form.get('session_type', 'Training')
    sets_data = request.form.get('sets_data', '[]')

    if not name:
        return {'ok': False, 'error': 'Set needs a name.'}, 400

    new_set = SavedSet(
        name=name,
        pool=pool,
        session_type=session_type,
        sets_data=sets_data,
        created_by=current_user.id
    )
    db.session.add(new_set)
    db.session.commit()
    return {'ok': True, 'id': new_set.id, 'name': new_set.name}


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


from functools import wraps
from flask import abort

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return wrapper


@main.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    from app import db
    from models import User, Swim, Session, SavedSet

    total_users = db.session.query(User).count()
    verified_users = db.session.query(User).filter_by(is_verified=True).count()
    unverified_users = total_users - verified_users
    total_swims = db.session.query(Swim).count()
    total_sessions = db.session.query(Session).count()
    users = db.session.query(User).order_by(User.created_at.desc()).all()

    return render_template(
        'admin_dashboard.html',
        total_users=total_users,
        verified_users=verified_users,
        unverified_users=unverified_users,
        total_swims=total_swims,
        total_sessions=total_sessions,
        users=users
    )

@main.route('/admin/sets')
@login_required
@admin_required
def admin_sets():
    from app import db
    from models import SavedSet

    sets = db.session.query(SavedSet).order_by(SavedSet.created_at.desc()).all()
    return render_template('admin_sets.html', sets=sets)

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

    if not name:
        flash('Set needs a name.', 'error')
        return redirect(url_for('main.admin_sets'))

    new_set = SavedSet(
        name=name,
        pool=pool,
        session_type=session_type,
        sets_data=sets_data,
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
        flash('Set deleted.', 'success')
    return redirect(url_for('main.admin_sets'))