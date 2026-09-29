"""Background task orchestration for long-running voice cloning jobs."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional

from loguru import logger

from src.config import config
from src.exceptions import ConfigurationError
from src.services.model_service_profiles import fetch_model_profile
from src.services.document_service import DocumentIngestService
from src.services.task_store import TaskStore
from src.voice import VoiceCloner


class TaskManager:
    """Manage queued synthesis tasks and persist progress updates."""

    def __init__(self, store: TaskStore) -> None:
        self.store = store
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="voice-task")
        self._futures: Dict[str, Future[Any]] = {}
        self._lock = Lock()

    def create_task(
        self,
        task_id: str,
        source_path: Path,
        model_name: str,
        language: str,
        source_name: str,
        source_type: str,
        metadata: Optional[Dict[str, Any]] = None,
        voice_path: Optional[Path] = None,
        voice_profile: Optional[str] = None,
        synthesis_options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        model_profile = fetch_model_profile(model_name)
        try:
            max_chars_per_segment = config.service_max_chars_per_segment
        except ConfigurationError:
            max_chars_per_segment = model_profile.segmentation.max_chars_per_segment

        try:
            max_estimated_duration_seconds = config.service_max_estimated_duration_seconds
        except ConfigurationError:
            max_estimated_duration_seconds = (
                model_profile.segmentation.max_estimated_duration_seconds
            )

        document_service = DocumentIngestService(
            max_chars_per_segment=max_chars_per_segment,
            max_estimated_duration_seconds=max_estimated_duration_seconds,
            model_profile=model_profile,
        )
        segments = document_service.load_segments(source_path)
        task_dirs = self.store.prepare_task_dirs(task_id)

        manifest = {
            "task_id": task_id,
            "model_profile": model_profile.to_dict(),
            "segments": [
                {
                    "index": index,
                    **segment.to_dict(),
                    "status": "pending",
                    "audio_path": "",
                    "error": "",
                }
                for index, segment in enumerate(segments)
            ],
            "artifacts": {
                "source_path": str(source_path),
                "voice_path": str(voice_path) if voice_path else "",
                "output_dir": str(task_dirs["output_dir"]),
            },
            "recent_error": "",
        }

        task_metadata = dict(metadata or {})
        task_metadata["model_profile"] = model_profile.to_dict()
        task_metadata["synthesis_options"] = dict(synthesis_options or {})

        self.store.create_task(
            task_id=task_id,
            status="queued",
            model_name=model_name,
            language=language,
            source_name=source_name,
            source_type=source_type,
            source_path=source_path,
            output_dir=task_dirs["output_dir"],
            total_segments=len(segments),
            metadata=task_metadata,
            voice_path=voice_path,
            voice_profile=voice_profile,
        )
        self.store.save_manifest(task_id, manifest)
        self._schedule(task_id)
        return self.store.task_detail(task_id)

    def resume_task(self, task_id: str) -> Dict[str, Any]:
        manifest = self.store.load_manifest(task_id)
        for segment in manifest.get("segments", []):
            if segment["status"] in {"failed", "running"}:
                segment["status"] = "pending"
                segment["error"] = ""
        manifest["recent_error"] = ""
        self.store.save_manifest(task_id, manifest)
        self.store.update_task(task_id, status="queued", error_message="")
        self._schedule(task_id)
        return self.store.task_detail(task_id)

    def pause_task(self, task_id: str) -> Dict[str, Any]:
        task = self.store.get_task(task_id)
        if task["status"] in {"completed", "cancelled"}:
            return self.store.task_detail(task_id)
        self.store.update_task(task_id, status="paused", error_message="Paused by user")
        return self.store.task_detail(task_id)

    def cancel_task(self, task_id: str) -> Dict[str, Any]:
        self.store.update_task(task_id, status="cancelled", error_message="Cancelled by user")
        return self.store.task_detail(task_id)

    def _schedule(self, task_id: str) -> None:
        with self._lock:
            future = self._futures.get(task_id)
            if future and not future.done():
                return
            self._futures[task_id] = self._executor.submit(self._run_task, task_id)

    def _run_task(self, task_id: str) -> None:
        try:
            task_state = self.store.get_task(task_id)
            if task_state["status"] in {"paused", "cancelled"}:
                return
            self.store.update_task(task_id, status="running", error_message="")
            task = self.store.get_task(task_id)
            manifest = self.store.load_manifest(task_id)
            cloner = VoiceCloner(model_name=task["model_name"])
            output_dir = Path(task["output_dir"])
            output_dir.mkdir(parents=True, exist_ok=True)
            total_segments = len(manifest.get("segments", []))
            synthesis_options = dict(task.get("metadata", {}).get("synthesis_options") or {})

            for segment in manifest.get("segments", []):
                task_state = self.store.get_task(task_id)
                if task_state["status"] in {"cancelled", "paused"}:
                    return
                if segment["status"] == "completed":
                    continue

                segment["status"] = "running"
                segment["error"] = ""
                self.store.save_manifest(task_id, manifest)

                output_path = output_dir / f"{segment['segment_id']}.wav"
                try:
                    result = cloner.synthesize(
                        text=segment["text"],
                        output_path=str(output_path),
                        reference_audio=task["voice_path"] or None,
                        voice_profile=task["voice_profile"] or None,
                        language=task["language"] or None,
                        **synthesis_options,
                    )
                    segment["status"] = "completed"
                    segment["audio_path"] = Path(result).name
                except Exception as exc:
                    segment["status"] = "failed"
                    segment["error"] = str(exc)
                    manifest["recent_error"] = str(exc)
                    self.store.save_manifest(task_id, manifest)
                    completed = sum(item["status"] == "completed" for item in manifest["segments"])
                    self.store.update_progress(
                        task_id,
                        completed_segments=completed,
                        total_segments=total_segments,
                        status="failed",
                        error_message=str(exc),
                    )
                    logger.exception("Task {} failed", task_id)
                    return

                completed = sum(item["status"] == "completed" for item in manifest["segments"])
                self.store.save_manifest(task_id, manifest)
                task_state = self.store.get_task(task_id)
                if task_state["status"] in {"cancelled", "paused"}:
                    self.store.update_progress(
                        task_id,
                        completed_segments=completed,
                        total_segments=total_segments,
                        status=task_state["status"],
                        error_message=task_state["error_message"],
                    )
                    return
                self.store.update_progress(
                    task_id,
                    completed_segments=completed,
                    total_segments=total_segments,
                    status="running",
                )

            self.store.update_progress(
                task_id,
                completed_segments=total_segments,
                total_segments=total_segments,
                status="completed",
                error_message="",
            )
        finally:
            with self._lock:
                self._futures.pop(task_id, None)