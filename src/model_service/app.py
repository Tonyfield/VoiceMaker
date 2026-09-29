"""FastAPI app exposing a dedicated API for a single TTS model runtime."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import RLock, Thread
from typing import Any, Iterator, Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from loguru import logger
import numpy as np

from src.config import config
from src.exceptions import (
    AudioProcessingError,
    AudioTooShortError,
    ConfigurationError,
    EmptyTextError,
    InvalidAudioFormatError,
    ModelDownloadError,
    ModelLoadError,
    ModelNotFoundError,
    TextProcessingError,
    TTSBaseException,
)
from src.logger import setup_logger
from src.model_profiles import build_model_service_profile
from src.model_service.usage_docs import render_model_usage_markdown
from src.models.base import BaseTTSModel
from src.models.loader import canonical_model_name, get_model, list_model_catalog, model_runtime_status


class ModelServiceRuntime:
    """Manage a single local TTS model instance behind an API boundary."""

    def __init__(self, model_name: str, device: str = "auto") -> None:
        self.model_name = canonical_model_name(model_name)
        self.device = device
        self._model: Optional[BaseTTSModel] = None
        self._state_lock = RLock()
        self._load_lock = RLock()
        self._inference_lock = RLock()
        self._load_error: str = ""
        self._warming_up = False
        self._warmup_thread: Optional[Thread] = None

    @property
    def metadata(self) -> dict:
        """Return model metadata from the configured catalog."""
        catalog = list_model_catalog()
        if self.model_name not in catalog:
            raise ModelNotFoundError(
                f"Model '{self.model_name}' is not present in the model catalog"
            )
        return catalog[self.model_name]

    @property
    def is_loaded(self) -> bool:
        """Return whether the underlying model has been loaded."""
        with self._state_lock:
            return bool(self._model is not None and self._model.is_loaded)

    @property
    def is_warming_up(self) -> bool:
        """Return whether a background warmup or foreground load is in progress."""
        with self._state_lock:
            return self._warming_up

    def start_warmup(self) -> None:
        """Start background model warmup so startup can download and load eagerly."""
        with self._state_lock:
            if self.is_loaded or self._warming_up:
                return
            self._warming_up = True
            self._load_error = ""
            self._warmup_thread = Thread(
                target=self._run_warmup,
                name=f"voicecloner-warmup-{self.model_name}",
                daemon=True,
            )
            warmup_thread = self._warmup_thread

        assert warmup_thread is not None
        warmup_thread.start()

    def _run_warmup(self) -> None:
        try:
            logger.info("Starting background warmup for model service: {}", self.model_name)
            self.ensure_model_loaded()
            logger.info("Model service warmup completed: {}", self.model_name)
        except Exception as exc:
            logger.warning("Model service warmup failed for {}: {}", self.model_name, exc)

    def health(self) -> dict:
        """Return current service health and local runtime availability."""
        runtime_available, runtime_error = model_runtime_status(self.model_name)
        status = "warming_up"
        if not runtime_available or self._load_error:
            status = "degraded"
        elif self.is_loaded:
            status = "ok"
        return {
            "status": status,
            "model_name": self.model_name,
            "loaded": self.is_loaded,
            "warming_up": self.is_warming_up,
            "runtime_available": runtime_available,
            "runtime_error": runtime_error or "",
            "load_error": self._load_error,
            "requires_reference": bool(self.metadata.get("requires_reference", False)),
        }

    def profile(self) -> dict:
        profile = build_model_service_profile(self.model_name, metadata=self.metadata)
        return profile.to_dict()

    def usage_markdown(self) -> str:
        return render_model_usage_markdown(
            model_name=self.model_name,
            metadata=self.metadata,
            profile=self.profile(),
        )

    @staticmethod
    def _normalize_model_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
        model_kwargs: dict[str, Any] = {}
        for key, value in kwargs.items():
            if isinstance(value, str):
                value = value.strip()
                if not value:
                    continue
            elif isinstance(value, bool):
                if not value:
                    continue
            elif value is None:
                continue
            model_kwargs[key] = value
        return model_kwargs

    @staticmethod
    def _chunk_to_pcm_s16le_bytes(chunk: Any) -> bytes:
        pcm = np.asarray(chunk, dtype=np.float32)
        if pcm.ndim == 0:
            pcm = pcm.reshape(1)
        if pcm.ndim > 1:
            pcm = np.mean(pcm, axis=-1)
        pcm = np.clip(pcm, -1.0, 1.0)
        scaled = np.where(pcm >= 0, pcm * 32767.0, pcm * 32768.0)
        return scaled.astype("<i2", copy=False).tobytes()

    def ensure_model_loaded(self) -> BaseTTSModel:
        """Load the model on demand and return the active instance."""
        with self._state_lock:
            if self._model is not None and self._model.is_loaded:
                return self._model

        with self._load_lock:
            with self._state_lock:
                if self._model is not None and self._model.is_loaded:
                    return self._model
                self._warming_up = True

            try:
                model = get_model(self.model_name, device=self.device)
                model.load_model()
            except Exception as exc:
                with self._state_lock:
                    self._load_error = str(exc)
                    self._warming_up = False
                raise

            with self._state_lock:
                self._model = model
                self._load_error = ""
                self._warming_up = False
                return model

    def synthesize(
        self,
        text: str,
        language: Optional[str] = None,
        reference_audio_name: str = "",
        reference_audio_bytes: bytes | None = None,
        **kwargs: Any,
    ) -> bytes:
        """Run local synthesis and return audio bytes."""
        if self.is_warming_up and not self.is_loaded:
            raise ModelLoadError(
                f"Model '{self.model_name}' is still warming up. Please retry shortly.",
                {"model_name": self.model_name},
            )

        model = self.ensure_model_loaded()
        with self._inference_lock:
            with TemporaryDirectory(prefix="voicecloner-model-") as temp_dir:
                output_path = Path(temp_dir) / "output.wav"
                model_kwargs = self._normalize_model_kwargs(kwargs)

                if reference_audio_bytes:
                    reference_name = reference_audio_name or "reference.wav"
                    reference_path = Path(temp_dir) / Path(reference_name).name
                    reference_path.write_bytes(reference_audio_bytes)
                    result = model.synthesize_with_voice(
                        text=text,
                        reference_audio=str(reference_path),
                        output_path=str(output_path),
                        language=language,
                        **model_kwargs,
                    )
                else:
                    result = model.synthesize(
                        text=text,
                        output_path=str(output_path),
                        language=language,
                        **model_kwargs,
                    )

                return Path(result).read_bytes()

    def stream_synthesize(
        self,
        text: str,
        language: Optional[str] = None,
        reference_audio_name: str = "",
        reference_audio_bytes: bytes | None = None,
        **kwargs: Any,
    ) -> tuple[int, Iterator[bytes]]:
        """Run local streaming synthesis and return PCM chunk bytes."""
        if self.is_warming_up and not self.is_loaded:
            raise ModelLoadError(
                f"Model '{self.model_name}' is still warming up. Please retry shortly.",
                {"model_name": self.model_name},
            )

        model = self.ensure_model_loaded()

        def _iter_chunks() -> Iterator[tuple[int, bytes]]:
            with self._inference_lock:
                with TemporaryDirectory(prefix="voicecloner-model-") as temp_dir:
                    model_kwargs = self._normalize_model_kwargs(kwargs)

                    if reference_audio_bytes:
                        stream_method = getattr(model, "stream_synthesize_with_voice", None)
                        if not callable(stream_method):
                            raise AudioProcessingError(
                                f"Model '{self.model_name}' does not support streaming voice synthesis.",
                                {"model_name": self.model_name},
                            )
                        reference_name = reference_audio_name or "reference.wav"
                        reference_path = Path(temp_dir) / Path(reference_name).name
                        reference_path.write_bytes(reference_audio_bytes)
                        chunk_iter = stream_method(
                            text=text,
                            reference_audio=str(reference_path),
                            language=language,
                            **model_kwargs,
                        )
                    else:
                        stream_method = getattr(model, "stream_synthesize", None)
                        if not callable(stream_method):
                            raise AudioProcessingError(
                                f"Model '{self.model_name}' does not support streaming synthesis.",
                                {"model_name": self.model_name},
                            )
                        chunk_iter = stream_method(
                            text=text,
                            language=language,
                            **model_kwargs,
                        )

                    for chunk, sample_rate in chunk_iter:
                        yield int(sample_rate), self._chunk_to_pcm_s16le_bytes(chunk)

        chunk_iter = _iter_chunks()
        try:
            sample_rate, first_chunk = next(chunk_iter)
        except StopIteration as exc:
            raise AudioProcessingError(
                f"Model '{self.model_name}' returned no audio chunks during streaming synthesis.",
                {"model_name": self.model_name},
            ) from exc

        def _payload_iter() -> Iterator[bytes]:
            yield first_chunk
            for _, payload in chunk_iter:
                yield payload

        return sample_rate, _payload_iter()


async def _read_reference_upload(reference_audio: Optional[UploadFile]) -> tuple[bytes | None, str]:
    reference_bytes = None
    reference_name = ""
    if reference_audio is not None and reference_audio.filename:
        reference_bytes = await reference_audio.read()
        reference_name = reference_audio.filename
    return reference_bytes, reference_name


async def _collect_request_options(
    request: Request,
    *,
    raw_options: dict[str, Any],
    skip_keys: set[str],
) -> dict[str, Any]:
    form = await request.form()
    for key, value in form.multi_items():
        if key in skip_keys:
            continue
        if isinstance(value, UploadFile):
            continue
        if key == "x_vector_only_mode":
            raw_options[key] = str(value).strip().lower() in {"1", "true", "on", "yes"}
            continue
        raw_options[key] = value
    return raw_options


def _http_status_for_exception(exc: TTSBaseException) -> int:
    """Map domain exceptions to HTTP status codes."""
    if isinstance(exc, (ConfigurationError, ModelLoadError, ModelDownloadError)):
        return 503
    if isinstance(exc, (ModelNotFoundError, InvalidAudioFormatError, AudioTooShortError, EmptyTextError, TextProcessingError)):
        return 400
    if isinstance(exc, AudioProcessingError):
        return 500
    return 500


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not config._config:
        config.load()
    app.title = f"{config.app_name} Model Service"
    app.version = config.app_version
    setup_logger(
        log_dir=str(config.log_dir),
        app_name="tts-vc-model-service",
        console_level="INFO",
        file_level="DEBUG",
        retention=config.log_retention,
        max_size=config.log_max_size,
    )
    model_name = os.getenv("VOICECLONER_MODEL_NAME", config.model_default)
    device = os.getenv("VOICECLONER_MODEL_DEVICE", "auto")
    app.state.runtime = ModelServiceRuntime(model_name=model_name, device=device)
    app.state.runtime.start_warmup()
    yield


app = FastAPI(lifespan=lifespan)


def _runtime() -> ModelServiceRuntime:
    return app.state.runtime


@app.get("/api/health")
async def health() -> dict:
    payload = _runtime().health()
    payload["app"] = {
        "name": config.app_name,
        "version": config.app_version,
    }
    return payload


@app.get("/api/profile")
async def profile() -> dict:
    return _runtime().profile()


@app.get("/api/usage")
async def usage() -> Response:
    return Response(content=_runtime().usage_markdown(), media_type="text/markdown")


@app.post("/api/synthesize")
async def synthesize(
    request: Request,
    text: str = Form(...),
    language: str = Form(""),
    voice_instruction: str = Form(""),
    speaker: str = Form(""),
    reference_text: str = Form(""),
    x_vector_only_mode: bool = Form(False),
    reference_audio: Optional[UploadFile] = File(None),
) -> Response:
    try:
        reference_bytes, reference_name = await _read_reference_upload(reference_audio)

        raw_options: dict[str, Any] = {
            "voice_instruction": voice_instruction,
            "speaker": speaker,
            "reference_text": reference_text,
            "x_vector_only_mode": x_vector_only_mode,
        }
        raw_options = await _collect_request_options(
            request,
            raw_options=raw_options,
            skip_keys={"text", "language", "reference_audio", "voice_instruction", "speaker", "reference_text", "x_vector_only_mode"},
        )

        audio_bytes = _runtime().synthesize(
            text=text,
            language=language or None,
            reference_audio_name=reference_name,
            reference_audio_bytes=reference_bytes,
            **raw_options,
        )
        return Response(content=audio_bytes, media_type="audio/wav")
    except TTSBaseException as exc:
        raise HTTPException(status_code=_http_status_for_exception(exc), detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/synthesize/stream")
async def synthesize_stream(
    request: Request,
    text: str = Form(...),
    language: str = Form(""),
    voice_instruction: str = Form(""),
    speaker: str = Form(""),
    reference_text: str = Form(""),
    x_vector_only_mode: bool = Form(False),
    emit_every_frames: int = Form(8),
    decode_window_frames: int = Form(80),
    overlap_samples: int = Form(512),
    reference_audio: Optional[UploadFile] = File(None),
) -> StreamingResponse:
    try:
        reference_bytes, reference_name = await _read_reference_upload(reference_audio)

        raw_options: dict[str, Any] = {
            "voice_instruction": voice_instruction,
            "speaker": speaker,
            "reference_text": reference_text,
            "x_vector_only_mode": x_vector_only_mode,
            "emit_every_frames": emit_every_frames,
            "decode_window_frames": decode_window_frames,
            "overlap_samples": overlap_samples,
        }
        raw_options = await _collect_request_options(
            request,
            raw_options=raw_options,
            skip_keys={
                "text",
                "language",
                "reference_audio",
                "voice_instruction",
                "speaker",
                "reference_text",
                "x_vector_only_mode",
                "emit_every_frames",
                "decode_window_frames",
                "overlap_samples",
            },
        )

        sample_rate, audio_stream = _runtime().stream_synthesize(
            text=text,
            language=language or None,
            reference_audio_name=reference_name,
            reference_audio_bytes=reference_bytes,
            **raw_options,
        )
        return StreamingResponse(
            audio_stream,
            media_type=f"audio/L16;rate={sample_rate};channels=1",
            headers={
                "X-Audio-Sample-Rate": str(sample_rate),
                "X-Audio-Format": "pcm_s16le",
                "X-Audio-Channels": "1",
                "Cache-Control": "no-cache",
            },
        )
    except TTSBaseException as exc:
        raise HTTPException(status_code=_http_status_for_exception(exc), detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc