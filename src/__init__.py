"""
TTS Voice Cloning - A text-to-speech application with voice cloning support.

Supports multiple TTS models with both CLI and GUI interfaces.
"""
from src.config import config
from src.logger import get_logger, setup_logger
from src.exceptions import (
    TTSBaseException,
    ModelError,
    ModelLoadError,
    ModelNotLoadedError,
    ModelNotFoundError,
    ModelServiceError,
    AudioError,
    AudioProcessingError,
    InvalidAudioFormatError,
    AudioTooShortError,
    VoiceError,
    VoiceProfileError,
    VoiceProfileNotFoundError,
    TextError,
    TextProcessingError,
    EmptyTextError,
    ConfigurationError,
)

__all__ = [
    "config",
    "get_logger",
    "setup_logger",
    "TTSBaseException",
    "ModelError",
    "ModelLoadError",
    "ModelNotLoadedError",
    "ModelNotFoundError",
    "ModelServiceError",
    "AudioError",
    "AudioProcessingError",
    "InvalidAudioFormatError",
    "AudioTooShortError",
    "VoiceError",
    "VoiceProfileError",
    "VoiceProfileNotFoundError",
    "TextError",
    "TextProcessingError",
    "EmptyTextError",
    "ConfigurationError",
    "cli",
    "cli_main",
    "__version__",
]


def _current_version() -> str:
    """Expose the currently loaded app version without duplicating a hard-coded constant."""
    if config._config:
        return config.app_version
    return "unknown"


def __getattr__(name: str):
    """Provide lazy access to CLI exports to avoid package import cycles."""
    if name == "__version__":
        return _current_version()
    if name == "cli":
        from src.cli import cli as cli_group

        return cli_group
    if name == "cli_main":
        from src.cli import main as cli_entrypoint

        return cli_entrypoint
    raise AttributeError(f"module 'src' has no attribute {name!r}")
