# wsgi.py — production entrypoint for gunicorn (Render's start command:
# `gunicorn wsgi:app`). Kept separate from app.py so importing app.py
# elsewhere (preview_app.py, test_systems.py) never triggers a second,
# unwanted app build.
from app import create_app

app = create_app()
