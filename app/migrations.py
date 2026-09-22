from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine


def run_startup_migrations(engine: Engine) -> None:
    # Lightweight SQLite-friendly migration for new MVP columns/tables.
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS job_events (
                    id INTEGER PRIMARY KEY,
                    job_id INTEGER NOT NULL,
                    stage VARCHAR(64) DEFAULT 'info',
                    level VARCHAR(16) DEFAULT 'info',
                    message TEXT DEFAULT '',
                    progress FLOAT DEFAULT 0.0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(job_id) REFERENCES jobs(id)
                )
                """
            )
        )

        for ddl in [
            "ALTER TABLE jobs ADD COLUMN progress FLOAT DEFAULT 0.0",
            "ALTER TABLE jobs ADD COLUMN attempts INTEGER DEFAULT 0",
            "ALTER TABLE jobs ADD COLUMN processed_scenes INTEGER DEFAULT 0",
            "ALTER TABLE jobs ADD COLUMN total_scenes INTEGER DEFAULT 0",
            "ALTER TABLE jobs ADD COLUMN queue_job_id VARCHAR(128) DEFAULT ''",
            "ALTER TABLE jobs ADD COLUMN last_error TEXT DEFAULT ''",
        ]:
            try:
                conn.execute(text(ddl))
            except Exception:
                # Column already exists.
                pass

