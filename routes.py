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
    return render_template('dashboard.html')