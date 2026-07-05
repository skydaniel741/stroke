# app.py
from flask import Flask
from extension import db, bcrypt, login_manager, oauth  # Imported from extensions
from dotenv import load_dotenv
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv()

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
        'DATABASE_URL',
        f"sqlite:///{os.path.join(BASE_DIR, 'stroke.db')}"
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['RESEND_API_KEY'] = os.getenv('RESEND_API_KEY')

    # Initialize extensions with the app
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'main.login'

    # ── Social sign-in (config-gated: providers only register when
    #    credentials exist in .env) ──
    oauth.init_app(app)
    app.config['GOOGLE_AUTH_ENABLED'] = False
    app.config['APPLE_AUTH_ENABLED'] = False

    if os.getenv('GOOGLE_CLIENT_ID') and os.getenv('GOOGLE_CLIENT_SECRET'):
        oauth.register(
            name='google',
            client_id=os.getenv('GOOGLE_CLIENT_ID'),
            client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
            server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
            client_kwargs={'scope': 'openid email profile'},
        )
        app.config['GOOGLE_AUTH_ENABLED'] = True

    if os.getenv('APPLE_CLIENT_ID') and os.getenv('APPLE_CLIENT_SECRET'):
        oauth.register(
            name='apple',
            client_id=os.getenv('APPLE_CLIENT_ID'),
            client_secret=os.getenv('APPLE_CLIENT_SECRET'),
            authorize_url='https://appleid.apple.com/auth/authorize',
            access_token_url='https://appleid.apple.com/auth/token',
            jwks_uri='https://appleid.apple.com/auth/keys',
            client_kwargs={
                'scope': 'openid email name',
                'response_mode': 'form_post',
                'token_endpoint_auth_method': 'client_secret_post',
            },
        )
        app.config['APPLE_AUTH_ENABLED'] = True

    with app.app_context():
        from models import User

        @login_manager.user_loader
        def load_user(user_id):
            return db.session.get(User, int(user_id))

        from routes import main
        app.register_blueprint(main)

        db.create_all()

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, port=int(os.getenv('PORT', 5000)))