"""Small SQLite project store for DuckSuite.

Project content stays in JSON files later; this database only holds the project
index and operational state. It is intentionally single-user and local.
"""

from __future__ import annotations

import os
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any


class ProjectStore:
    def __init__(self, data_root: Path):
        self.data_root = Path(data_root).expanduser().resolve()
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.path = self.data_root / "state.db"
        self._init()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _init(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    source_bytes INTEGER NOT NULL DEFAULT 0,
                    created REAL NOT NULL,
                    updated REAL NOT NULL
                )
                """
            )

    def _row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "source_path": row["source_path"],
            "source_bytes": row["source_bytes"],
            "created": row["created"],
            "updated": row["updated"],
        }

    def create(self, name: str, source_path: str | Path) -> dict[str, Any]:
        source = Path(source_path).expanduser().resolve()
        if not source.is_file():
            raise FileNotFoundError(str(source))
        if not source.is_relative_to(self.data_root):
            raise ValueError("Source must be inside the DuckSuite data folder.")

        project_id = f"prj_{secrets.token_hex(6)}"
        now = time.time()
        clean_name = " ".join(str(name or "").split()).strip() or source.stem
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO projects (id, name, source_path, source_bytes, created, updated)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    clean_name[:160],
                    str(source),
                    source.stat().st_size,
                    now,
                    now,
                ),
            )
        return self.get(project_id)

    def list(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM projects ORDER BY updated DESC"
            ).fetchall()
        return [self._row(row) for row in rows]

    def get(self, project_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM projects WHERE id = ?", (project_id,)
            ).fetchone()
        if row is None:
            raise KeyError(project_id)
        return self._row(row)

    def rename(self, project_id: str, name: str) -> dict[str, Any]:
        clean_name = " ".join(str(name or "").split()).strip()
        if not clean_name:
            raise ValueError("Project name cannot be empty.")
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE projects SET name = ?, updated = ? WHERE id = ?",
                (clean_name[:160], time.time(), project_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(project_id)
        return self.get(project_id)

    def delete(self, project_id: str) -> None:
        project = self.get(project_id)
        source = Path(project["source_path"])
        with self._connect() as connection:
            connection.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        if source.is_relative_to(self.data_root) and source.is_file():
            try:
                source.unlink()
                parent = source.parent
                if parent != self.data_root and parent.is_dir() and not any(parent.iterdir()):
                    parent.rmdir()
            except OSError:
                pass
