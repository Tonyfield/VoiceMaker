"""FastAPI application for the voice cloning service."""

from __future__ import annotations

import asyncio
import shutil
import time
import uuid
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from typing import Any, Optional
from zipfile import ZIP_DEFLATED, ZipFile

import httpx
from fastapi import Body, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from loguru import logger

from src.config import config
from src.exceptions import ConfigurationError, ModelServiceError, VoiceProfileError, VoiceProfileNotFoundError
from src.logger import setup_logger
from src.models.loader import list_model_catalog
from src.services import TaskManager, TaskStore
from src.services.model_service_profiles import fetch_model_profile, fetch_model_profile_async
from src.voice.profile import VoiceProfile, VoiceProfileManager


STATIC_DIR = Path(__file__).parent / "static"
HEALTH_INFO_LOG_INTERVAL_SECONDS = 600.0
_last_health_info_log_at = 0.0


def _health_log_monotonic() -> float:
    return time.monotonic()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not config._config:
        config.load()
    app.title = config.app_name
    app.version = config.app_version
    setup_logger(
        log_dir=str(config.log_dir),
        app_name="tts-vc-service",
        level=config.log_level,
        retention=config.log_retention,
        max_size=config.log_max_size,
    )
    store = TaskStore(config.data_dir)
    if config.service_reset_interrupted_tasks_on_start:
        store.reset_interrupted_tasks()
    app.state.store = store
    app.state.manager = TaskManager(store)
    app.state.profile_manager = VoiceProfileManager()
    yield


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _store() -> TaskStore:
    return app.state.store


def _manager() -> TaskManager:
    return app.state.manager


def _profile_manager() -> VoiceProfileManager:
    return app.state.profile_manager


def _write_upload(upload: UploadFile, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as file_handle:
        shutil.copyfileobj(upload.file, file_handle)
    return destination


def _service_error_message(exc: Exception) -> str:
    """Convert a model service probe error into a concise string."""
    if isinstance(exc, httpx.HTTPStatusError):
        response = exc.response
        body = response.text.strip()
        return body or f"HTTP {response.status_code}"
    return str(exc)


def _voice_profile_to_dict(profile: VoiceProfile) -> dict[str, Any]:
    payload = profile.to_dict()
    payload["audio_url"] = f"/api/voice-profiles/{profile.name}/audio"
    return payload


def _normalize_file_hash(file_hash: str) -> str:
    normalized = str(file_hash or "").strip().lower()
    if not normalized:
        raise HTTPException(status_code=400, detail="Reference audio hash is required")
    return normalized


async def _store_uploaded_voice_asset(asset_file: UploadFile, file_hash: str = "") -> dict[str, Any]:
    if asset_file is None or not asset_file.filename:
        raise HTTPException(status_code=400, detail="Reference audio file is required")
    data = await asset_file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Reference audio file is empty")
    try:
        return _profile_manager().store_asset_bytes(
            data=data,
            original_name=asset_file.filename,
            expected_hash=_normalize_file_hash(file_hash) if file_hash else None,
            content_type=asset_file.content_type or "",
        )
    except VoiceProfileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _normalize_task_options(
    model_name: str,
    model_profile,
    raw_options: dict[str, Any],
) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for field in model_profile.task_inputs:
        name = str(field.get("name") or "").strip()
        if not name or name not in raw_options:
            continue

        field_type = str(field.get("type") or "text").strip().lower()
        if field_type == "checkbox":
            value = bool(raw_options.get(name, False))
            if value:
                normalized[name] = True
            continue

        value = str(raw_options.get(name) or "").strip()
        if bool(field.get("required")) and not value:
            raise HTTPException(
                status_code=400,
                detail=f"Field '{name}' is required for model '{model_name}'",
            )
        if value:
            normalized[name] = value

    if model_name == "qwen3_tts_base":
        if not normalized.get("x_vector_only_mode") and not normalized.get("reference_text"):
            raise HTTPException(
                status_code=400,
                detail="Model 'qwen3_tts_base' requires reference_text unless x_vector_only_mode is enabled",
            )

    return normalized


def _iter_voice_profiles() -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    manager = _profile_manager()
    for name in manager.list_profiles():
        try:
            profiles.append(_voice_profile_to_dict(manager.load(name)))
        except Exception:
            continue
    return profiles


def _task_artifact_items(task_id: str) -> list[dict[str, Any]]:
    detail = _store().task_detail(task_id)
    output_dir = Path(detail["output_dir"])
    items: list[dict[str, Any]] = []
    for segment in detail.get("segments", []):
        file_name = str(segment.get("audio_path") or "").strip()
        if not file_name:
            continue
        artifact_path = output_dir / file_name
        if not artifact_path.exists():
            continue
        items.append(
            {
                "segment_id": segment.get("segment_id", ""),
                "title": segment.get("title", ""),
                "file_name": file_name,
                "size": artifact_path.stat().st_size,
                "download_url": f"/artifacts/{task_id}/{file_name}",
                "text_preview": str(segment.get("text") or "")[:96],
            }
        )
    return items


async def _probe_model_service(
    client: httpx.AsyncClient,
    model_name: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """Probe a configured remote model service and merge live health into metadata."""
    item = {"name": model_name, **metadata}

    try:
        service_url = config.model_service_url(model_name).rstrip("/")
    except ConfigurationError as exc:
        logger.warning(
            f"TTS service '{model_name}' is misconfigured and will be skipped: {exc}"
        )
        item.update(
            {
                "service_url": "",
                "service_status": "misconfigured",
                "runtime_available": False,
                "service_loaded": False,
                "service_probe_error": str(exc),
                "profile": None,
                "profile_error": str(exc),
                "enabled": False,
            }
        )
        return item

    health_url = f"{service_url}/api/health"
    item["service_url"] = service_url

    try:
        response = await client.get(health_url)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning(
            f"Failed to probe TTS service '{model_name}' at {health_url}: {_service_error_message(exc)}"
        )
        item.update(
            {
                "service_status": "unreachable",
                "runtime_available": False,
                "service_loaded": False,
                "service_probe_error": _service_error_message(exc),
                "profile": None,
                "profile_error": _service_error_message(exc),
                "enabled": False,
            }
        )
        return item

    service_status = str(payload.get("status") or "unknown")
    runtime_available = bool(payload.get("runtime_available", service_status == "ok"))
    service_loaded = bool(payload.get("loaded", False))
    load_error = str(payload.get("load_error") or "")
    runtime_error = str(payload.get("runtime_error") or "")

    profile_payload: dict[str, Any] | None = None
    profile_error = ""
    try:
        profile = await fetch_model_profile_async(client, model_name)
        profile_payload = profile.to_dict()
    except Exception as exc:
        profile_error = str(exc)
        logger.warning(
            f"Failed to fetch TTS service profile for '{model_name}' from {service_url}: {profile_error}"
        )

    live_enabled = (
        bool(metadata.get("enabled"))
        and metadata.get("implemented", False)
        and service_status == "ok"
        and runtime_available
        and not profile_error
    )

    item.update(
        {
            "service_status": service_status,
            "runtime_available": runtime_available,
            "service_loaded": service_loaded,
            "service_probe_error": "",
            "load_error": load_error,
            "runtime_error": runtime_error,
            "service_model_name": str(payload.get("model_name") or model_name),
            "profile": profile_payload,
            "profile_error": profile_error,
            "enabled": live_enabled,
        }
    )
    return item


async def _live_model_items() -> list[dict[str, Any]]:
    """Return model catalog items enriched with live model-service health."""
    catalog = list_model_catalog()
    logger.info(
        f"Loading TTS service list for {len(catalog)} configured models: {', '.join(catalog.keys())}"
    )
    async with httpx.AsyncClient(timeout=config.model_service_request_timeout_seconds) as client:
        tasks = [
            _probe_model_service(client=client, model_name=name, metadata=metadata)
            for name, metadata in catalog.items()
        ]
        items = await asyncio.gather(*tasks)

    reachable_count = sum(1 for item in items if item.get("service_status") != "unreachable")
    enabled_count = sum(1 for item in items if item.get("enabled"))
    loaded_count = sum(1 for item in items if item.get("service_loaded"))
    logger.info(
        "Loaded TTS service list: "
        f"total={len(items)}, reachable={reachable_count}, enabled={enabled_count}, loaded={loaded_count}"
    )
    return items


def _log_health_payload(payload: dict[str, Any]) -> None:
    global _last_health_info_log_at

    logger.debug(
        "Health endpoint requested: "
        f"default_model={payload.get('default_model')}, service_port={payload.get('service_port')}, "
        f"poll_interval_seconds={payload.get('poll_interval_seconds')}"
    )

    now = _health_log_monotonic()
    if now - _last_health_info_log_at >= HEALTH_INFO_LOG_INTERVAL_SECONDS:
        logger.info(
            "Health endpoint summary: "
            f"default_model={payload.get('default_model')}, service_port={payload.get('service_port')}, "
            f"poll_interval_seconds={payload.get('poll_interval_seconds')}"
        )
        _last_health_info_log_at = now


@app.get("/")
async def index() -> HTMLResponse:
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    version = config.app_version
    html = html.replace("__APP_VERSION__", version)
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


@app.get("/api/health")
async def health() -> dict:
    payload = {
        "status": "ok",
        "app": {
            "name": config.app_name,
            "version": config.app_version,
        },
        "default_model": config.model_default,
        "service_port": config.service_port,
        "poll_interval_seconds": config.service_poll_interval_seconds,
    }
    _log_health_payload(payload)
    return payload


@app.get("/api/models")
async def models() -> dict:
    return {
        "default": config.model_default,
        "items": await _live_model_items(),
    }


@app.get("/api/models/{model_name}/profile")
async def model_profile(model_name: str) -> dict:
    catalog = list_model_catalog()
    if model_name not in catalog:
        raise HTTPException(status_code=404, detail="Unknown model")
    async with httpx.AsyncClient(timeout=config.model_service_request_timeout_seconds) as client:
        try:
            profile = await fetch_model_profile_async(client, model_name)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    return profile.to_dict()


@app.get("/api/voice-profiles")
async def voice_profiles() -> dict:
    return {"items": _iter_voice_profiles()}


@app.post("/api/voice-assets/lookup")
async def lookup_voice_asset(payload: dict = Body(...)) -> dict:
    file_hash = _normalize_file_hash(str(payload.get("file_hash") or ""))
    manager = _profile_manager()
    if not manager.asset_exists(file_hash):
        return {"exists": False, "file_hash": file_hash}
    return {"exists": True, "asset": manager.get_asset_info(file_hash)}


@app.post("/api/voice-assets")
async def upload_voice_asset(
    file_hash: str = Form(...),
    asset_file: UploadFile = File(...),
) -> dict:
    normalized_hash = _normalize_file_hash(file_hash)
    existed = _profile_manager().asset_exists(normalized_hash)
    asset = await _store_uploaded_voice_asset(asset_file=asset_file, file_hash=normalized_hash)
    return {"exists": existed, "asset": asset}


@app.get("/api/voice-assets/{file_hash}/audio")
async def voice_asset_audio(file_hash: str) -> FileResponse:
    normalized_hash = _normalize_file_hash(file_hash)
    try:
        asset_path = _profile_manager().get_asset_path(normalized_hash)
        asset_info = _profile_manager().get_asset_info(normalized_hash)
    except VoiceProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Voice asset not found") from exc
    return FileResponse(asset_path, media_type=asset_info.get("content_type") or None)


@app.get("/api/voice-profiles/{name}")
async def voice_profile_detail(name: str) -> dict:
    try:
        return _voice_profile_to_dict(_profile_manager().load(name))
    except VoiceProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Voice profile not found") from exc


@app.get("/api/voice-profiles/{name}/audio")
async def voice_profile_audio(name: str) -> FileResponse:
    try:
        profile = _profile_manager().load(name)
    except VoiceProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Voice profile not found") from exc

    audio_path = Path(profile.reference_audio)
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="Reference audio not found")
    return FileResponse(audio_path)


@app.post("/api/voice-profiles")
async def create_voice_profile(
    name: str = Form(...),
    language: str = Form("auto"),
    description: str = Form(""),
    reference_audio_hash: str = Form(""),
    reference_audio: Optional[UploadFile] = File(None),
) -> dict:
    manager = _profile_manager()
    existing_profile: Optional[VoiceProfile] = manager.load(name) if manager.exists(name) else None
    metadata = dict(existing_profile.metadata) if existing_profile else {}

    destination: Optional[Path] = None
    normalized_hash = str(reference_audio_hash or "").strip().lower()

    if reference_audio is not None and reference_audio.filename:
        asset = await _store_uploaded_voice_asset(reference_audio, normalized_hash)
        normalized_hash = asset["file_hash"]
        destination = manager.get_asset_path(normalized_hash)
        metadata.update({
            "reference_audio_hash": normalized_hash,
            "original_filename": asset.get("original_name") or reference_audio.filename,
        })
    elif normalized_hash:
        try:
            destination = manager.get_asset_path(_normalize_file_hash(normalized_hash))
        except VoiceProfileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Reference audio asset not found") from exc
        asset = manager.get_asset_info(normalized_hash)
        metadata.update({
            "reference_audio_hash": normalized_hash,
            "original_filename": asset.get("original_name") or destination.name,
        })
    elif existing_profile is not None:
        destination = Path(existing_profile.reference_audio)
    else:
        raise HTTPException(status_code=400, detail="Reference audio is required for a new voice profile")

    profile = manager.create_profile(
        name=name,
        reference_audio=str(destination),
        language=language,
        description=description,
        metadata=metadata,
    )
    return _voice_profile_to_dict(profile)


@app.delete("/api/voice-profiles/{name}")
async def delete_voice_profile(name: str) -> dict:
    try:
        _profile_manager().load(name)
    except VoiceProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Voice profile not found") from exc
    _profile_manager().delete(name)
    return {"deleted": True, "name": name}


@app.get("/api/tasks")
async def list_tasks() -> dict:
    return {"items": _store().list_tasks()}


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str) -> dict:
    try:
        return _store().task_detail(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc


@app.post("/api/tasks")
async def create_task(
    request: Request,
    source_file: UploadFile = File(...),
    voice_file: Optional[UploadFile] = File(None),
    model_name: str = Form(default=None),
    language: str = Form("auto"),
    voice_profile: str = Form(""),
    voice_instruction: str = Form(""),
    speaker: str = Form(""),
    reference_text: str = Form(""),
    x_vector_only_mode: bool = Form(False),
) -> JSONResponse:
    selected_model = model_name or config.model_default
    catalog = list_model_catalog()
    if selected_model not in catalog:
        raise HTTPException(status_code=400, detail="Unknown model")
    if not catalog[selected_model].get("implemented", False):
        raise HTTPException(status_code=400, detail=f"Model '{selected_model}' is not implemented in this build")

    try:
        model_profile = fetch_model_profile(selected_model)
    except ModelServiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    raw_options: dict[str, Any] = {
        "voice_instruction": voice_instruction,
        "speaker": speaker,
        "reference_text": reference_text,
        "x_vector_only_mode": x_vector_only_mode,
    }
    form = await request.form()
    for key, value in form.multi_items():
        if key in {"source_file", "voice_file", "model_name", "language", "voice_profile"}:
            continue
        if isinstance(value, UploadFile):
            continue
        if key == "x_vector_only_mode":
            raw_options[key] = str(value).strip().lower() in {"1", "true", "on", "yes"}
            continue
        raw_options[key] = value

    synthesis_options = _normalize_task_options(
        model_name=selected_model,
        model_profile=model_profile,
        raw_options=raw_options,
    )

    task_id = uuid.uuid4().hex
    task_dirs = _store().prepare_task_dirs(task_id)
    source_path = _write_upload(source_file, task_dirs["upload_dir"] / source_file.filename)
    voice_path = None
    active_voice_profile = voice_profile.strip() if model_profile.requires_reference else ""

    if model_profile.requires_reference and voice_file is not None and voice_file.filename:
        voice_path = _write_upload(voice_file, task_dirs["upload_dir"] / voice_file.filename)

    if model_profile.requires_reference and voice_path is None and not active_voice_profile:
        raise HTTPException(
            status_code=400,
            detail=f"Model '{selected_model}' requires reference audio or a saved voice profile",
        )

    try:
        task = _manager().create_task(
            task_id=task_id,
            source_path=source_path,
            model_name=selected_model,
            language=language,
            source_name=source_file.filename,
            source_type=source_path.suffix.lower(),
            metadata={"source_size": source_path.stat().st_size},
            voice_path=voice_path,
            voice_profile=active_voice_profile or None,
            synthesis_options=synthesis_options,
        )
    except ModelServiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return JSONResponse(task, status_code=201)


@app.post("/api/tasks/{task_id}/resume")
async def resume_task(task_id: str) -> dict:
    try:
        return _manager().resume_task(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc


@app.post("/api/tasks/{task_id}/pause")
async def pause_task(task_id: str) -> dict:
    try:
        return _manager().pause_task(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc


@app.post("/api/tasks/{task_id}/cancel")
async def cancel_task(task_id: str) -> dict:
    try:
        return _manager().cancel_task(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc


@app.get("/artifacts/{task_id}/{file_name}")
async def task_artifact(task_id: str, file_name: str) -> FileResponse:
    try:
        task = _store().get_task(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    artifact_path = Path(task["output_dir"]) / file_name
    if not artifact_path.exists():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(artifact_path)


@app.get("/api/tasks/{task_id}/artifacts")
async def task_artifacts(task_id: str) -> dict:
    try:
        _store().get_task(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    return {"items": _task_artifact_items(task_id)}


@app.post("/api/tasks/{task_id}/artifacts/download")
async def download_task_artifacts(task_id: str, payload: dict = Body(...)) -> Response:
    try:
        _store().get_task(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc

    requested_files = [str(item) for item in payload.get("files", []) if str(item).strip()]
    if not requested_files:
        raise HTTPException(status_code=400, detail="No artifact files selected")

    detail = _store().task_detail(task_id)
    output_dir = Path(detail["output_dir"])
    archive_buffer = BytesIO()
    found = 0
    with ZipFile(archive_buffer, mode="w", compression=ZIP_DEFLATED) as archive:
        for file_name in requested_files:
            artifact_path = output_dir / file_name
            if artifact_path.exists() and artifact_path.is_file():
                archive.write(artifact_path, arcname=file_name)
                found += 1

    if found == 0:
        raise HTTPException(status_code=404, detail="Artifacts not found")

    return Response(
        content=archive_buffer.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{task_id}-artifacts.zip"',
        },
    )


@app.post("/api/tasks/{task_id}/artifacts/delete")
async def delete_task_artifacts(task_id: str, payload: dict = Body(...)) -> dict:
    try:
        detail = _store().task_detail(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc

    requested_files = {str(item) for item in payload.get("files", []) if str(item).strip()}
    if not requested_files:
        raise HTTPException(status_code=400, detail="No artifact files selected")

    output_dir = Path(detail["output_dir"])
    manifest = _store().load_manifest(task_id)
    deleted_count = 0

    for segment in manifest.get("segments", []):
        file_name = str(segment.get("audio_path") or "")
        if file_name not in requested_files:
            continue
        artifact_path = output_dir / file_name
        if artifact_path.exists() and artifact_path.is_file():
            artifact_path.unlink()
            deleted_count += 1
        segment["audio_path"] = ""

    _store().save_manifest(task_id, manifest)
    return {"deleted": deleted_count}