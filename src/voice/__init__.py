"""
Voice module for TTS Voice Cloning.
Provides voice cloning and profile management functionality.
"""
from src.voice.profile import VoiceProfile, VoiceProfileManager
from src.voice.processor import AudioProcessor
from src.voice.cloner import VoiceCloner

__all__ = [
    "VoiceProfile",
    "VoiceProfileManager",
    "AudioProcessor",
    "VoiceCloner",
]
