import json
import re

from flask_login import UserMixin
from datetime import datetime
import random
from app import db, bcrypt

class User(db.Model, UserMixin):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    plan = db.Column(db.String(20), default='free')
    is_verified = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)
    verify_code = db.Column(db.String(6), nullable=True)
    verify_code_sent_at = db.Column(db.DateTime, nullable=True)
    role = db.Column(db.String(20), default='swimmer')  # 'swimmer' or 'coach'
    share_leaderboard = db.Column(db.Boolean, default=False)

    def set_password(self, password):
        self.password = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password, password)

    def generate_verify_code(self):
        self.verify_code = str(random.randint(100000, 999999))
        self.verify_code_sent_at = datetime.utcnow()
        return self.verify_code

    swims = db.relationship('Swim', backref='user', lazy=True)
    sessions = db.relationship('Session', backref='user', lazy=True)


class Swim(db.Model):
    __tablename__ = 'swim'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    event = db.Column(db.String(50), nullable=False)
    pool = db.Column(db.String(10))
    stroke = db.Column(db.String(10))
    time = db.Column(db.String(20))
    notes = db.Column(db.Text)
    logged_at = db.Column(db.DateTime, default=datetime.utcnow)
    tag = db.Column(db.String(10), default='practice')  # 'practice' or 'meet'
    splits = db.Column(db.Text)  # JSON list of 50m split strings, optional

    def get_splits(self):
        try:
            return json.loads(self.splits or '[]')
        except (ValueError, TypeError):
            return []

    def time_in_seconds(self):
        t = self.time
        if not t:
            return None
        try:
            if ':' in t:
                mins, rest = t.split(':')
                return int(mins) * 60 + float(rest)
            return float(t)
        except:
            return None

    def distance(self):
        if not self.event:
            return 0
        match = re.match(r'\s*(\d+)', self.event)
        return int(match.group(1)) if match else 0


class Session(db.Model):
    __tablename__ = 'session'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    session_type = db.Column(db.String(50))
    pool = db.Column(db.String(10))
    sets_data = db.Column(db.Text)
    notes = db.Column(db.Text)
    logged_at = db.Column(db.DateTime, default=datetime.utcnow)

    def get_sets(self):
        try:
            return json.loads(self.sets_data or '[]')
        except:
            return []

    def total_distance(self):
        total = 0
        for s in self.get_sets():
            try:
                total += int(s.get('reps', 0)) * int(s.get('dist', 0))
            except:
                pass
        return total


class Goal(db.Model):
    __tablename__ = 'goal'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    event = db.Column(db.String(50), nullable=False)
    pool = db.Column(db.String(10))
    target_time = db.Column(db.String(20), nullable=False)
    target_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def target_seconds(self):
        t = self.target_time
        if not t:
            return None
        try:
            if ':' in t:
                mins, rest = t.split(':')
                return int(mins) * 60 + float(rest)
            return float(t)
        except (ValueError, TypeError):
            return None


class AthleteProfile(db.Model):
    """The Solo-tier onboarding questionnaire answers plus the AI-generated
    training program built from them. One row per user -- redoing the
    questionnaire overwrites it (see routes_solo.solo_onboarding)."""
    __tablename__ = 'athlete_profile'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    level = db.Column(db.String(30))  # Beginner/Intermediate/Advanced/Competitive
    age = db.Column(db.Integer)
    training_days_per_week = db.Column(db.Integer)
    fitness_ability = db.Column(db.String(30))  # self-rated: Low/Moderate/Good/High
    primary_stroke = db.Column(db.String(20))
    main_goal = db.Column(db.Text)
    program_json = db.Column(db.Text)  # AI-generated program, see ai_utils.generate_training_program
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    def get_program(self):
        try:
            return json.loads(self.program_json or '{}')
        except (ValueError, TypeError):
            return {}


class CheckIn(db.Model):
    """A swimmer's periodic (typically daily) reflection: how training felt
    and what could improve, plus an AI-generated insight in response."""
    __tablename__ = 'check_in'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    checkin_date = db.Column(db.Date, nullable=False)
    feeling_rating = db.Column(db.Integer)  # 1-5
    notes = db.Column(db.Text)
    ai_insight = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Standard(db.Model):
    """A public qualifying-standard reference time, e.g. a NAG cut or a
    club/regional qualifying time. Admin-managed. Used both for free-tier
    'compare against a standard' and coach-tier squad-promotion flags."""
    __tablename__ = 'standard'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)   # e.g. "NAG 12 & Under"
    event = db.Column(db.String(50), nullable=False)
    pool = db.Column(db.String(10), default='25m')
    gender = db.Column(db.String(10), default='open')  # 'men', 'women', 'open'
    age_group = db.Column(db.String(30))
    cutoff_time = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def cutoff_seconds(self):
        t = self.cutoff_time
        if not t:
            return None
        try:
            if ':' in t:
                mins, rest = t.split(':')
                return int(mins) * 60 + float(rest)
            return float(t)
        except (ValueError, TypeError):
            return None


class AdminAuditLog(db.Model):
    __tablename__ = 'admin_audit_log'

    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    action = db.Column(db.String(50), nullable=False)
    target_type = db.Column(db.String(30))
    target_id = db.Column(db.Integer)
    detail = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Announcement(db.Model):
    """squad_id NULL = platform-wide banner (posted by an admin).
    squad_id set = a coach's one-way announcement board for that squad."""
    __tablename__ = 'announcement'

    id = db.Column(db.Integer, primary_key=True)
    squad_id = db.Column(db.Integer, db.ForeignKey('squad.id'), nullable=True)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class TrainingProgram(db.Model):
    """Solo-tier content library: dryland/strength/mobility/core programs
    and nutrition/fueling suggestions. Same flexible shape serves both."""
    __tablename__ = 'training_program'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(30), default='Strength')  # Strength/Mobility/Core/Nutrition
    description = db.Column(db.Text)
    content_blocks = db.Column(db.Text)  # JSON: [{heading, body, reps?, sets?, rest?}]
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def get_blocks(self):
        try:
            return json.loads(self.content_blocks or '[]')
        except (ValueError, TypeError):
            return []


class Club(db.Model):
    """Groups multiple squads under one club-level owner (multi-squad admin view).
    A coach's first club is auto-active; any club after that needs admin approval
    (status='pending') before the coach can use it -- see routes_coach.club_create."""
    __tablename__ = 'club'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    age_range = db.Column(db.String(50))
    contact_email = db.Column(db.String(150))
    newsletter_url = db.Column(db.String(255))
    status = db.Column(db.String(20), default='active')  # 'active' or 'pending'
    approved_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    squads = db.relationship('Squad', backref='club', lazy=True)


class Squad(db.Model):
    __tablename__ = 'squad'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    coach_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    club_id = db.Column(db.Integer, db.ForeignKey('club.id'), nullable=True)
    invite_code = db.Column(db.String(20), unique=True, nullable=False)
    base_fee = db.Column(db.Numeric(10, 2), default=0)
    per_swimmer_fee = db.Column(db.Numeric(10, 2), default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    memberships = db.relationship('SquadMembership', backref='squad', lazy=True)

    def active_member_count(self):
        return sum(1 for m in self.memberships if m.status == 'active')

    def billing_estimate(self):
        base = float(self.base_fee or 0)
        per = float(self.per_swimmer_fee or 0)
        return base + per * self.active_member_count()


class SquadMembership(db.Model):
    __tablename__ = 'squad_membership'

    id = db.Column(db.Integer, primary_key=True)
    squad_id = db.Column(db.Integer, db.ForeignKey('squad.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    invited_email = db.Column(db.String(150))
    status = db.Column(db.String(20), default='invited')  # invited/pending_consent/active/declined
    lane_group = db.Column(db.String(30))
    requires_consent = db.Column(db.Boolean, default=False)
    joined_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    swimmer = db.relationship('User', foreign_keys=[user_id])


class ConsentRecord(db.Model):
    """Parental consent for a minor swimmer joining a squad. Placeholder
    copy only -- needs legal review before this is relied on in production."""
    __tablename__ = 'consent_record'

    id = db.Column(db.Integer, primary_key=True)
    membership_id = db.Column(db.Integer, db.ForeignKey('squad_membership.id'), nullable=False)
    guardian_name = db.Column(db.String(120))
    guardian_email = db.Column(db.String(150))
    consent_given = db.Column(db.Boolean, default=False)
    consent_requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    consent_given_at = db.Column(db.DateTime, nullable=True)


class CoachNote(db.Model):
    """Coach-private note about a swimmer. Never shown to the swimmer."""
    __tablename__ = 'coach_note'

    id = db.Column(db.Integer, primary_key=True)
    squad_id = db.Column(db.Integer, db.ForeignKey('squad.id'), nullable=False)
    swimmer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    coach_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    note = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class StatusFlag(db.Model):
    """Injury / availability status for a swimmer within a squad."""
    __tablename__ = 'status_flag'

    id = db.Column(db.Integer, primary_key=True)
    squad_id = db.Column(db.Integer, db.ForeignKey('squad.id'), nullable=False)
    swimmer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(20), default='available')  # available/injured/limited
    note = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_by = db.Column(db.Integer, db.ForeignKey('user.id'))


class SquadEvent(db.Model):
    """A scheduled practice/meet/event on a squad's coach-facing calendar."""
    __tablename__ = 'squad_event'

    id = db.Column(db.Integer, primary_key=True)
    squad_id = db.Column(db.Integer, db.ForeignKey('squad.id'), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    event_date = db.Column(db.Date, nullable=False)
    event_time = db.Column(db.String(20))  # free text, e.g. '6:00 AM'
    event_type = db.Column(db.String(20), default='practice')  # practice/meet/other
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class SavedSet(db.Model):
    __tablename__ = 'saved_set'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    pool = db.Column(db.String(10), default='25m')
    session_type = db.Column(db.String(50), default='Training')
    sets_data = db.Column(db.Text)  # JSON string, same shape as sessionSets in log.html
    category = db.Column(db.String(30), default='Fitness')
    description = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def get_sets(self):
        try:
            return json.loads(self.sets_data or '[]')
        except:
            return []

    def total_distance(self):
        total = 0
        for s in self.get_sets():
            try:
                total += int(s.get('reps', 0)) * int(s.get('dist', 0))
            except:
                pass
        return total

