"""Persistent task storage for the FastAPI service."""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class TaskStore:
    """Persist task summaries in SQLite and segment manifests on disk."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.tasks_dir = self.data_dir / "tasks"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "tasks.db"
        self._lock = threading.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    language TEXT,
                    source_name TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    voice_path TEXT,
                    voice_profile TEXT,
                    progress REAL NOT NULL,
                    total_segments INTEGER NOT NULL,
                    completed_segments INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    error_message TEXT NOT NULL,
                    output_dir TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                )
                """
            )
            connection.commit()

    def prepare_task_dirs(self, task_id: str) -> Dict[str, Path]:
        task_dir = self.tasks_dir / task_id
        upload_dir = task_dir / "uploads"
        output_dir = task_dir / "output"
        upload_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)
        return {"task_dir": task_dir, "upload_dir": upload_dir, "output_dir": output_dir}

    def create_task(
        self,
        task_id: str,
        status: str,
        model_name: str,
        language: str,
        source_name: str,
        source_type: str,
        source_path: Path,
        output_dir: Path,
        total_segments: int,
        metadata: Optional[Dict[str, Any]] = None,
        voice_path: Optional[Path] = None,
        voice_profile: Optional[str] = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        payload = (
            task_id,
            status,
            model_name,
            language,
            source_name,
            source_type,
            str(source_path),
            str(voice_path) if voice_path else None,
            voice_profile,
            0.0,
            total_segments,
            0,
            now,
            now,
            "",
            str(output_dir),
            json.dumps(metadata or {}, ensure_ascii=False),
        )
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO tasks (
                    id, status, model_name, language, source_name, source_type,
                    source_path, voice_path, voice_profile, progress,
                    total_segments, completed_segments, created_at, updated_at,
                    error_message, output_dir, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                payload,
            )
            connection.commit()

    def save_manifest(self, task_id: str, manifest: Dict[str, Any]) -> None:
        manifest_path = self._manifest_path(task_id)
        with self._lock:
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = manifest_path.with_suffix(".tmp")
            temp_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            temp_path.replace(manifest_path)

    def load_manifest(self, task_id: str) -> Dict[str, Any]:
        return json.loads(self._manifest_path(task_id).read_text(encoding="utf-8"))

    def get_task(self, task_id: str) -> Dict[str, Any]:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            raise KeyError(task_id)
        return self._row_to_task(row)

    def list_tasks(self, limit: int = 50) -> List[Dict[str, Any]]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_task(row) for row in rows]

    def update_task(self, task_id: str, **fields: Any) -> None:
        if not fields:
            return
        fields["updated_at"] = datetime.now(timezone.utc).isoformat()
        assignments = ", ".join(f"{key} = ?" for key in fields)
        values = list(fields.values()) + [task_id]
        with closing(self._connect()) as connection:
            connection.execute(
                f"UPDATE tasks SET {assignments} WHERE id = ?",
                values,
            )
            connection.commit()

    def update_progress(
        self,
        task_id: str,
        completed_segments: int,
        total_segments: int,
        status: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        progress = round((completed_segments / total_segments) * 100, 2) if total_segments else 0.0
        update_fields: Dict[str, Any] = {
            "completed_segments": completed_segments,
            "total_segments": total_segments,
            "progress": progress,
        }
        if status is not None:
            update_fields["status"] = status
        if error_message is not None:
            update_fields["error_message"] = error_message
        self.update_task(task_id, **update_fields)

    def reset_interrupted_tasks(self) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                """
                UPDATE tasks
                SET status = 'paused',
                    error_message = 'Service restarted before the task finished.',
                    updated_at = ?
                WHERE status IN ('queued', 'running')
                """,
                (datetime.now(timezone.utc).isoformat(),),
            )
            connection.commit()

    def task_detail(self, task_id: str) -> Dict[str, Any]:
        task = self.get_task(task_id)
        manifest = self.load_manifest(task_id)
        task["segments"] = manifest.get("segments", [])
        task["artifacts"] = manifest.get("artifacts", {})
        task["recent_error"] = manifest.get("recent_error", "")
        return task

    def _manifest_path(self, task_id: str) -> Path:
        return self.tasks_dir / task_id / "manifest.json"

    def _row_to_task(self, row: sqlite3.Row) -> Dict[str, Any]:
        task = dict(row)
        task["metadata"] = json.loads(task.pop("metadata_json") or "{}")
        return task