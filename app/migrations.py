from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine


def run_startup_migrations(engine: Engine) -> None:
    # Lightweight SQLite-friendly migration for new MVP columns/tables.
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS music_generations (
                    id INTEGER PRIMARY KEY,
                    title VARCHAR(255) DEFAULT 'Untitled Track',
                    user_prompt TEXT NOT NULL,
                    composed_prompt TEXT NOT NULL,
                    model VARCHAR(255) DEFAULT '',
                    mood VARCHAR(64) DEFAULT '',
                    style VARCHAR(64) DEFAULT '',
                    energy VARCHAR(32) DEFAULT '',
                    instrumentation VARCHAR(255) DEFAULT '',
                    duration_seconds INTEGER DEFAULT 8,
                    status VARCHAR(32) DEFAULT 'ready',
                    audio_path VARCHAR(512) DEFAULT '',
                    generation_time_ms INTEGER DEFAULT 0,
                    sample_rate INTEGER DEFAULT 32000,
                    parent_generation_id INTEGER NULL,
                    error_message TEXT DEFAULT '',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(parent_generation_id) REFERENCES music_generations(id)
                )
                """
            )
        )

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

