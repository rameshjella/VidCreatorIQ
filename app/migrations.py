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

        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS character_profiles (
                    id INTEGER PRIMARY KEY,
                    project_id INTEGER NOT NULL,
                    name VARCHAR(128) DEFAULT 'Character',
                    identity_prompt TEXT DEFAULT '',
                    lora_adapter VARCHAR(255) DEFAULT '',
                    lora_strength FLOAT DEFAULT 0.8,
                    notes TEXT DEFAULT '',
                    FOREIGN KEY(project_id) REFERENCES projects(id)
                )
                """
            )
        )

        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS scene_characters (
                    id INTEGER PRIMARY KEY,
                    scene_id INTEGER NOT NULL,
                    character_id INTEGER NOT NULL,
                    role VARCHAR(64) DEFAULT 'support',
                    weight FLOAT DEFAULT 1.0,
                    FOREIGN KEY(scene_id) REFERENCES scenes(id),
                    FOREIGN KEY(character_id) REFERENCES character_profiles(id)
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
            "ALTER TABLE music_generations ADD COLUMN retry_of_generation_id INTEGER NULL",
            "ALTER TABLE music_generations ADD COLUMN queue_job_id VARCHAR(128) DEFAULT ''",
            "ALTER TABLE music_generations ADD COLUMN cancel_requested INTEGER DEFAULT 0",
            # Render pipeline v2: measured narration timing + richer artifacts.
            "ALTER TABLE scenes ADD COLUMN audio_duration_seconds FLOAT DEFAULT 0.0",
            "ALTER TABLE scenes ADD COLUMN tts_provider VARCHAR(64) DEFAULT ''",
            "ALTER TABLE scenes ADD COLUMN tts_voice VARCHAR(128) DEFAULT ''",
            "ALTER TABLE jobs ADD COLUMN output_audio_path VARCHAR(512) DEFAULT ''",
            "ALTER TABLE jobs ADD COLUMN output_subtitle_path VARCHAR(512) DEFAULT ''",
            "ALTER TABLE jobs ADD COLUMN output_poster_path VARCHAR(512) DEFAULT ''",
            "ALTER TABLE jobs ADD COLUMN output_duration_seconds FLOAT DEFAULT 0.0",
            "ALTER TABLE projects ADD COLUMN character_identity_prompt TEXT DEFAULT ''",
            "ALTER TABLE projects ADD COLUMN character_lora_tags TEXT DEFAULT ''",
            "ALTER TABLE jobs ADD COLUMN output_music_path VARCHAR(512) DEFAULT ''",
            "ALTER TABLE jobs ADD COLUMN output_sfx_path VARCHAR(512) DEFAULT ''",
            "ALTER TABLE jobs ADD COLUMN output_stems_manifest_path VARCHAR(512) DEFAULT ''",
            "ALTER TABLE jobs ADD COLUMN output_stems_zip_path VARCHAR(512) DEFAULT ''",
        ]:
            try:
                conn.execute(text(ddl))
            except Exception:
                # Column already exists.
                pass

        # Backfill one default character profile from legacy project-level fields.
        conn.execute(
            text(
                """
                INSERT INTO character_profiles (project_id, name, identity_prompt, lora_adapter, lora_strength, notes)
                SELECT p.id,
                       'Lead',
                       COALESCE(p.character_identity_prompt, ''),
                       CASE
                           WHEN instr(COALESCE(p.character_lora_tags, ''), ',') > 0
                           THEN substr(COALESCE(p.character_lora_tags, ''), 1, instr(COALESCE(p.character_lora_tags, ''), ',') - 1)
                           ELSE COALESCE(p.character_lora_tags, '')
                       END,
                       0.8,
                       'Backfilled from legacy project identity fields'
                FROM projects p
                WHERE (COALESCE(p.character_identity_prompt, '') <> '' OR COALESCE(p.character_lora_tags, '') <> '')
                  AND NOT EXISTS (
                      SELECT 1 FROM character_profiles c WHERE c.project_id = p.id
                  )
                """
            )
        )

