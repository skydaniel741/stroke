from sqlalchemy import text

# Columns added to existing tables after their initial release.
# db.create_all() only creates missing tables, not missing columns on
# tables that already exist, so anything added to an existing model here
# needs a matching entry below.
NEW_COLUMNS = {
    'user': [
        ("role", "VARCHAR(20) DEFAULT 'swimmer'"),
        ("share_leaderboard", "BOOLEAN DEFAULT 0"),
    ],
    'swim': [
        ("tag", "VARCHAR(10) DEFAULT 'practice'"),
        ("splits", "TEXT"),
    ],
    'club': [
        ("age_range", "VARCHAR(50)"),
        ("contact_email", "VARCHAR(150)"),
        ("newsletter_url", "VARCHAR(255)"),
        ("status", "VARCHAR(20) DEFAULT 'active'"),
        ("approved_at", "DATETIME"),
    ],
    'squad': [
        ("color", "VARCHAR(20) DEFAULT 'blue'"),
    ],
    'squad_event': [
        ("slot", "VARCHAR(10) DEFAULT ''"),
        ("saved_set_id", "INTEGER"),
    ],
    'session': [
        ("source", "VARCHAR(20) DEFAULT 'self'"),
        ("squad_event_id", "INTEGER"),
    ],
    'athlete_profile': [
        ("coaching_tone", "VARCHAR(20) DEFAULT 'balanced'"),
        ("intensity", "VARCHAR(20) DEFAULT 'normal'"),
        ("regen_week_start", "DATE"),
        ("regen_count", "INTEGER DEFAULT 0"),
    ],
}


def run_migrations(db):
    """Add any missing columns to already-existing SQLite tables. Safe to
    call on every startup -- checks PRAGMA table_info before altering."""
    with db.engine.connect() as conn:
        existing_tables = {
            row[0] for row in conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ))
        }
        for table, columns in NEW_COLUMNS.items():
            if table not in existing_tables:
                continue  # table will be created fresh by db.create_all(), columns included
            current_cols = {
                row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))
            }
            for col_name, col_def in columns:
                if col_name not in current_cols:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}"))
        conn.commit()
