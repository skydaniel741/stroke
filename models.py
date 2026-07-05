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

