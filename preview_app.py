# preview_app.py — runs the app on port 5001 for Claude's preview verification,
# so it doesn't collide with the dev server on 5000. Safe to delete.
from app import create_app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='127.0.0.1', port=5001, use_reloader=False)
