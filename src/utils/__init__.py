"""
Utility functions for TTS Voice Cloning.
"""
from src.utils.audio import (
    SUPPORTED_FORMATS,
    is_supported_format,
    get_audio_info,
    convert_audio,
    normalize_audio,
    split_audio,
    concatenate_audio,
    validate_reference_audio,
)
from src.utils.text import (
    clean_text,
    split_text,
    detect_language,
    estimate_speech_duration,
    format_text_for_tts,
    validate_text,
)
from src.utils.xhtml_segmenter import XHTMLSegmenter
from src.utils.tts_converter import TTSConverter

__all__ = [
    # Audio utilities
    "SUPPORTED_FORMATS",
    "is_supported_format",
    "get_audio_info",
    "convert_audio",
    "normalize_audio",
    "split_audio",
    "concatenate_audio",
    "validate_reference_audio",
    # Text utilities
    "clean_text",
    "split_text",
    "detect_language",
    "estimate_speech_duration",
    "format_text_for_tts",
    "validate_text",
    # Book processing utilities
    "XHTMLSegmenter",
    "TTSConverter",
]