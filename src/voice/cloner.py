"""
Voice cloning engine for TTS synthesis.
"""
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import httpx

from loguru import logger

from src.config import config
from src.models.loader import canonical_model_name, list_model_catalog
from src.voice.profile import VoiceProfile, VoiceProfileManager
from src.voice.processor import AudioProcessor
from src.exceptions import AudioProcessingError, ModelNotFoundError, ModelServiceError, VoiceProfileNotFoundError


class VoiceCloner:
    """
    Voice cloning engine that combines TTS models with voice profiles.
    
    Provides a high-level interface for:
    - Synthesizing speech with cloned voices
    - Managing voice profiles
    - Processing reference audio
    """
    
    def __init__(
        self,
        model_name: Optional[str] = None,
        device: str = "auto"
    ) -> None:
        """
        Initialize the voice cloner.
        
        Args:
            model_name: TTS model to use (uses config default if not provided)
            device: Device for inference
        """
        self.model_name = canonical_model_name(model_name or config.model_default)
        self.device = device
        self._profile_manager: Optional[VoiceProfileManager] = None
        self._audio_processor: Optional[AudioProcessor] = None
        self._clients: Dict[str, httpx.Client] = {}
        self._model_catalog: Optional[Dict[str, Dict[str, Any]]] = None

    def _switch_model(self, model_name: Optional[str]) -> None:
        """Swap the active model instance when the requested model changes."""
        if model_name:
            self.model_name = canonical_model_name(model_name)

    def _catalog(self) -> Dict[str, Dict[str, Any]]:
        """Get the configured model catalog."""
        if self._model_catalog is None:
            self._model_catalog = list_model_catalog()
        return self._model_catalog

    def _model_metadata(self, model_name: str) -> Dict[str, Any]:
        """Return catalog metadata for a canonical model name."""
        catalog = self._catalog()
        if model_name not in catalog:
            raise ModelNotFoundError(
                f"Model '{model_name}' not found",
                {"available_models": list(catalog.keys())},
            )
        return catalog[model_name]

    def _client(self, model_name: str) -> httpx.Client:
        """Return a cached HTTP client for a remote model service."""
        service_url = config.model_service_url(model_name).rstrip("/")
        client = self._clients.get(model_name)
        if client is None or str(client.base_url).rstrip("/") != service_url:
            if client is not None:
                client.close()
            client = httpx.Client(
                base_url=service_url,
                timeout=config.model_service_request_timeout_seconds,
            )
            self._clients[model_name] = client
        return client

    def _extract_remote_error(self, response: httpx.Response) -> str:
        """Extract a useful error message from a failed model service response."""
        try:
            payload = response.json()
        except ValueError:
            payload = None

        if isinstance(payload, dict):
            detail = payload.get("detail")
            if isinstance(detail, str) and detail.strip():
                return detail.strip()
        return response.text.strip() or f"HTTP {response.status_code}"

    def _request_synthesis(
        self,
        model_name: str,
        text: str,
        output_path: Path,
        reference_audio: Optional[Union[str, Path]] = None,
        language: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Send a synthesis request to the dedicated remote model service."""
        client = self._client(model_name)
        data = {"text": text}
        if language:
            data["language"] = language
        for key, value in kwargs.items():
            if value in (None, ""):
                continue
            if isinstance(value, bool):
                if value:
                    data[key] = "true"
                continue
            data[key] = str(value)

        try:
            if reference_audio:
                audio_path = Path(reference_audio)
                with audio_path.open("rb") as handle:
                    response = client.post(
                        "/api/synthesize",
                        data=data,
                        files={
                            "reference_audio": (
                                audio_path.name,
                                handle,
                                "application/octet-stream",
                            )
                        },
                    )
            else:
                response = client.post("/api/synthesize", data=data)
        except httpx.HTTPError as exc:
            raise ModelServiceError(
                f"Remote model service '{model_name}' request failed: {exc}",
                {"model": model_name, "service_url": config.model_service_url(model_name)},
            ) from exc

        if response.is_error:
            raise ModelServiceError(
                f"Remote model service '{model_name}' returned {response.status_code}: {self._extract_remote_error(response)}",
                {"model": model_name, "status_code": response.status_code},
            )

        if not response.content:
            raise ModelServiceError(
                f"Remote model service '{model_name}' returned an empty audio payload",
                {"model": model_name},
            )

        output_path.write_bytes(response.content)
    
    @property
    def profile_manager(self) -> VoiceProfileManager:
        """Get the voice profile manager."""
        if self._profile_manager is None:
            self._profile_manager = VoiceProfileManager()
        return self._profile_manager
    
    @property
    def audio_processor(self) -> AudioProcessor:
        """Get the audio processor."""
        if self._audio_processor is None:
            self._audio_processor = AudioProcessor()
        return self._audio_processor
    
    def synthesize(
        self,
        text: str,
        output_path: Union[str, Path],
        reference_audio: Optional[Union[str, Path]] = None,
        voice_profile: Optional[str] = None,
        language: Optional[str] = None,
        model_name: Optional[str] = None,
        **kwargs
    ) -> Path:
        """
        Synthesize speech with optional voice cloning.
        
        Args:
            text: Text to synthesize
            output_path: Output file path
            reference_audio: Path to reference audio for voice cloning
            voice_profile: Name of saved voice profile
            language: Language code (auto-detect if not provided)
            **kwargs: Additional synthesis parameters
            
        Returns:
            Path to generated audio file
            
        Raises:
            VoiceProfileNotFoundError: If voice profile not found
            ModelNotLoadedError: If model fails to load
        """
        self._switch_model(model_name)
        active_model = self.model_name
        metadata = self._model_metadata(active_model)

        # Get reference audio from profile if specified
        if voice_profile and not reference_audio:
            profile = self.profile_manager.load(voice_profile)
            reference_audio = profile.reference_audio
            if not language:
                language = profile.language
            logger.info(f"Using voice profile: {voice_profile}")
        
        # Prepare output path
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        if not reference_audio and metadata.get("requires_reference", False):
            raise AudioProcessingError(
                f"Model '{active_model}' requires reference audio or a saved voice profile"
            )

        logger.info(f"Calling remote TTS model service: {active_model}")
        self._request_synthesis(
            model_name=active_model,
            text=text,
            output_path=output,
            reference_audio=reference_audio,
            language=language,
            **kwargs,
        )

        return output
    
    def create_voice_profile(
        self,
        name: str,
        reference_audio: Union[str, Path],
        language: str = "auto",
        description: str = ""
    ) -> VoiceProfile:
        """
        Create and save a voice profile.
        
        Args:
            name: Profile name
            reference_audio: Path to reference audio
            language: Language code
            description: Profile description
            
        Returns:
            Created voice profile
        """
        # Validate audio
        self.audio_processor.prepare_reference(reference_audio)
        
        # Create profile
        profile = self.profile_manager.create_profile(
            name=name,
            reference_audio=str(reference_audio),
            language=language,
            description=description
        )
        
        logger.success(f"Voice profile created: {name}")
        return profile
    
    def list_voice_profiles(self) -> List[str]:
        """
        List all saved voice profiles.
        
        Returns:
            List of profile names
        """
        return self.profile_manager.list_profiles()
    
    def get_voice_profile(self, name: str) -> VoiceProfile:
        """
        Get a voice profile by name.
        
        Args:
            name: Profile name
            
        Returns:
            Voice profile instance
            
        Raises:
            VoiceProfileNotFoundError: If profile not found
        """
        return self.profile_manager.load(name)
    
    def delete_voice_profile(self, name: str) -> bool:
        """
        Delete a voice profile.
        
        Args:
            name: Profile name to delete
            
        Returns:
            True if deleted successfully
            
        Raises:
            VoiceProfileNotFoundError: If profile not found
        """
        return self.profile_manager.delete(name)

    def close(self) -> None:
        """Close any cached remote HTTP clients."""
        for client in self._clients.values():
            client.close()
        self._clients.clear()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
