"""
Custom exceptions for TTS Voice Cloning application.
Provides specific exception types for different error scenarios.
"""
from typing import Optional, Any


class TTSBaseException(Exception):
    """Base exception for all TTS application errors."""
    
    def __init__(self, message: str, details: Optional[dict] = None):
        """
        Initialize the base exception.
        
        Args:
            message: Error message describing the exception.
            details: Optional dictionary with additional error details.
        """
        self.message = message
        self.details = details or {}
        super().__init__(self.message)
    
    def __str__(self) -> str:
        """Return string representation of the exception."""
        if self.details:
            return f"{self.message} | Details: {self.details}"
        return self.message


# Model-related exceptions
class ModelError(TTSBaseException):
    """Base exception for model-related errors."""
    pass


class ModelLoadError(ModelError):
    """Raised when a model fails to load."""
    pass


class ModelNotLoadedError(ModelError):
    """Raised when trying to use a model that hasn't been loaded."""
    pass


class ModelNotFoundError(ModelError):
    """Raised when a requested model is not found."""
    pass


class ModelDownloadError(ModelError):
    """Raised when model download fails from all sources."""
    pass


class ModelServiceError(ModelError):
    """Raised when a remote model service call fails."""
    pass


# Audio-related exceptions
class AudioError(TTSBaseException):
    """Base exception for audio-related errors."""
    pass


class AudioProcessingError(AudioError):
    """Raised when audio processing fails."""
    pass


class InvalidAudioFormatError(AudioError):
    """Raised when audio format is not supported."""
    pass


class AudioTooShortError(AudioError):
    """Raised when audio is too short for voice cloning."""
    pass


# Voice-related exceptions
class VoiceError(TTSBaseException):
    """Base exception for voice-related errors."""
    pass


class VoiceProfileError(VoiceError):
    """Raised when voice profile operations fail."""
    pass


class VoiceProfileNotFoundError(VoiceError):
    """Raised when a voice profile is not found."""
    pass


# Text-related exceptions
class TextError(TTSBaseException):
    """Base exception for text-related errors."""
    pass


class TextProcessingError(TextError):
    """Raised when text processing fails."""
    pass


class EmptyTextError(TextError):
    """Raised when text input is empty."""
    pass


# Configuration exceptions
class ConfigurationError(TTSBaseException):
    """Raised when configuration is invalid."""
    pass


# User-friendly error messages
ERROR_MESSAGES = {
    ModelLoadError: "Failed to load the TTS model. Please check your internet connection and try again.",
    ModelNotLoadedError: "The TTS model is not loaded. Please wait for the model to initialize.",
    ModelNotFoundError: "The requested model is not available. Please check the model name.",
    ModelDownloadError: "Failed to download the model from all sources. Please check your internet connection or try using a VPN.",
    ModelServiceError: "The remote TTS model service is unavailable or returned an error.",
    AudioProcessingError: "Failed to process the audio file. Please ensure the file is not corrupted.",
    InvalidAudioFormatError: "The audio format is not supported. Please use WAV or MP3 format.",
    AudioTooShortError: "The reference audio is too short. Please provide at least 6 seconds of audio.",
    VoiceProfileNotFoundError: "The voice profile was not found. Please check the profile name.",
    EmptyTextError: "The text input is empty. Please provide text to synthesize.",
    ConfigurationError: "Invalid configuration. Please check your config.yaml file.",
}


def get_user_friendly_message(error: Exception) -> str:
    """
    Get a user-friendly error message for an exception.
    
    Args:
        error: The exception that occurred.
        
    Returns:
        A user-friendly error message.
    """
    for error_type, message in ERROR_MESSAGES.items():
        if isinstance(error, error_type):
            return message
    return "An unexpected error occurred. Please try again."
