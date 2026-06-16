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
    

