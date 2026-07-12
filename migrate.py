from sqlalchemy import inspect, text

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
        ("swimmer_type", "VARCHAR(30)"),
        ("coaching_situation", "VARCHAR(40)"),
        ("coaching_focus", "TEXT"),
        ("eating_habits", "VARCHAR(30)"),
        ("limitations", "TEXT"),
        ("nutrition_json", "TEXT"),
        ("dryland_json", "TEXT"),
        ("progress_insight", "TEXT"),
        ("progress_insight_at", "DATETIME"),
    ],
    'saved_set': [
        ("difficulty", "VARCHAR(20) DEFAULT 'Medium'"),
        ("distance_focus", "VARCHAR(20) DEFAULT 'All'"),
    ],
    'check_in': [
        ("fatigue_rating", "INTEGER"),
        ("sleep_quality", "INTEGER"),
    ],
}


def _dialect_col_def(col_def, dialect_name):
    """NEW_COLUMNS defs are written in SQLite syntax; translate the bits
    Postgres doesn't accept."""
    if dialect_name != 'sqlite':
        col_def = col_def.replace('DATETIME', 'TIMESTAMP')
        col_def = col_def.replace('DEFAULT 0', 'DEFAULT FALSE').replace('DEFAULT 1', 'DEFAULT TRUE')
    return col_def


def run_migrations(db):
    """Add any missing columns to already-existing tables. Safe to call on
    every startup -- uses SQLAlchemy's inspector so it works on both
    SQLite (dev) and Postgres (prod)."""
    dialect_name = db.engine.dialect.name
    inspector = inspect(db.engine)
    existing_tables = set(inspector.get_table_names())

    with db.engine.connect() as conn:
        for table, columns in NEW_COLUMNS.items():
            if table not in existing_tables:
                continue  # table will be created fresh by db.create_all(), columns included
            current_cols = {col['name'] for col in inspector.get_columns(table)}
            for col_name, col_def in columns:
                if col_name not in current_cols:
                    col_def = _dialect_col_def(col_def, dialect_name)
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}"))
        conn.commit()
