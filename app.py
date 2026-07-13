# app.py
from flask import Flask
from extension import db, bcrypt, login_manager, oauth  # Imported from extensions
from dotenv import load_dotenv
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv()

def create_app():
    app = Flask(__name__)
    secret_key = os.getenv('SECRET_KEY')
    is_debug = os.getenv('FLASK_DEBUG', '').lower() in ('1', 'true', 'yes')
    if not secret_key:
        if not is_debug:
            raise RuntimeError(
                'SECRET_KEY environment variable is not set. Refusing to start '
                'with a guessable session-signing key outside of local dev.'
            )
        secret_key = 'dev-secret-key'
    app.config['SECRET_KEY'] = secret_key
    db_url = os.getenv('DATABASE_URL') or f"sqlite:///{os.path.join(BASE_DIR, 'stroke.db')}"
    # Render (and Heroku before it) hands out postgres:// connection strings,
    # but SQLAlchemy 1.4+ / psycopg2 require the postgresql:// scheme -- fix
    # it here so the DATABASE_URL can be pasted straight from the dashboard.
    if db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    # Render's managed Postgres drops idle connections; without pre-ping,
    # SQLAlchemy hands out a dead connection from the pool and every query
    # on it fails with "SSL SYSCALL error: EOF detected" instead of
    # transparently reconnecting.
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_pre_ping': True, 'pool_recycle': 280}
    # Hard cap on any request body (photo scans allow up to 20MB images);
    # anything bigger gets a clean 413 instead of tying up the worker.
    app.config['MAX_CONTENT_LENGTH'] = 25 * 1024 * 1024
    app.config['RESEND_API_KEY'] = os.getenv('RESEND_API_KEY')
    app.config['ANTHROPIC_API_KEY'] = os.getenv('ANTHROPIC_API_KEY')
    app.config['ANTHROPIC_MODEL'] = os.getenv('ANTHROPIC_MODEL', 'claude-sonnet-5')
    app.config['AI_SCAN_ENABLED'] = bool(os.getenv('ANTHROPIC_API_KEY'))

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
        from routes_solo import solo
        from routes_coach import coach
        app.register_blueprint(main)
        app.register_blueprint(solo)
        app.register_blueprint(coach)

        db.create_all()

        from migrate import run_migrations
        run_migrations(db)

    from ai_utils import render_coach_markdown
    app.jinja_env.filters['coach_markdown'] = render_coach_markdown

    # ── Graceful error handling: the site never shows a raw crash page.
    #    Bad input gets rejected upstream by validation.py; anything that
    #    still slips through lands here, gets logged for debugging, the DB
    #    session is rolled back so user data stays safe, and the visitor
    #    sees a friendly page instead of a stack trace. ──
    from flask import render_template

    @app.errorhandler(404)
    def not_found(e):
        return render_template('error.html', code=404,
                               message="That page doesn't exist."), 404

    @app.errorhandler(413)
    def too_large(e):
        return render_template('error.html', code=413,
                               message="That upload was too large."), 413

    @app.errorhandler(500)
    def server_error(e):
        app.logger.exception('Unhandled server error')
        try:
            db.session.rollback()
        except Exception:
            pass
        return render_template('error.html', code=500,
                               message="Something went wrong on our side. Your data is safe, try that again."), 500

    return app

if __name__ == '__main__':
    app = create_app()
    # FLASK_DEBUG must be explicitly set to '1'/'true' to enable the debugger --
    # it exposes a remote code-execution console, never run it against a public host.
    debug = os.getenv('FLASK_DEBUG', '').lower() in ('1', 'true', 'yes')
    # host='0.0.0.0' so phones on the same Wi-Fi can reach this dev server.
    app.run(debug=debug, host='0.0.0.0', port=int(os.getenv('PORT', 5000)))