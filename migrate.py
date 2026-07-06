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
