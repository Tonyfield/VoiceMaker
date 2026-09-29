"""
Audio processing utilities for voice cloning.
"""
from pathlib import Path
from typing import Optional, Tuple, Union

import numpy as np
from loguru import logger

from src.exceptions import (
    AudioProcessingError,
    AudioTooShortError,
    InvalidAudioFormatError,
)


class AudioProcessor:
    """
    Audio processor for handling audio files.
    
    Provides utilities for:
    - Loading and saving audio files
    - Resampling audio
    - Normalizing audio
    - Trimming silence
    """
    
    DEFAULT_SAMPLE_RATE = 24000
    
    def __init__(self, sample_rate: int = DEFAULT_SAMPLE_RATE) -> None:
        """
        Initialize audio processor.
        
        Args:
            sample_rate: Target sample rate for processing
        """
        self.sample_rate = sample_rate
    
    def load_audio(
        self,
        audio_path: Union[str, Path],
        target_sr: Optional[int] = None
    ) -> Tuple[np.ndarray, int]:
        """
        Load an audio file.
        
        Args:
            audio_path: Path to audio file
            target_sr: Target sample rate (uses self.sample_rate if not provided)
            
        Returns:
            Tuple of (audio_data, sample_rate)
            
        Raises:
            AudioProcessingError: If loading fails
            InvalidAudioFormatError: If audio file not found
        """
        try:
            import librosa
            
            path = Path(audio_path)
            if not path.exists():
                raise InvalidAudioFormatError(
                    f"Audio file not found: {audio_path}",
                    {"path": str(audio_path)}
                )
            
            target_sr = target_sr or self.sample_rate
            audio, sr = librosa.load(str(path), sr=target_sr, mono=True)
            
            logger.debug(
                f"Loaded audio: {path.name} (duration: {len(audio)/sr:.2f}s)"
            )
            return audio, sr
            
        except ImportError:
            raise AudioProcessingError(
                "librosa not installed. Please install it with: pip install librosa"
            )
        except Exception as e:
            if isinstance(e, InvalidAudioFormatError):
                raise
            raise AudioProcessingError(
                f"Failed to load audio: {e}",
                {"path": str(audio_path)}
            )
    
    def save_audio(
        self,
        audio: np.ndarray,
        output_path: Union[str, Path],
        sample_rate: Optional[int] = None
    ) -> Path:
        """
        Save audio to a file.
        
        Args:
            audio: Audio data as numpy array
            output_path: Output file path
            sample_rate: Sample rate (uses self.sample_rate if not provided)
            
        Returns:
            Path to saved file
            
        Raises:
            AudioProcessingError: If saving fails
        """
        try:
            import soundfile as sf
            
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            sr = sample_rate or self.sample_rate
            sf.write(str(path), audio, sr)
            
            logger.debug(f"Saved audio: {path}")
            return path
            
        except ImportError:
            raise AudioProcessingError(
                "soundfile not installed. Please install it with: pip install soundfile"
            )
        except Exception as e:
            raise AudioProcessingError(
                f"Failed to save audio: {e}",
                {"path": str(output_path)}
            )
    
    def get_duration(self, audio_path: Union[str, Path]) -> float:
        """
        Get the duration of an audio file.
        
        Args:
            audio_path: Path to audio file
            
        Returns:
            Duration in seconds
        """
        try:
            import librosa
            duration = librosa.get_duration(path=str(audio_path))
            return duration
        except Exception as e:
            logger.warning(f"Could not get audio duration: {e}")
            return 0.0
    
    def normalize(
        self,
        audio: np.ndarray,
        target_db: float = -3.0
    ) -> np.ndarray:
        """
        Normalize audio to target dB level.
        
        Args:
            audio: Audio data
            target_db: Target dB level
            
        Returns:
            Normalized audio
        """
        # Calculate current RMS
        rms = np.sqrt(np.mean(audio ** 2))
        
        if rms == 0:
            return audio
        
        # Calculate target RMS
        target_rms = 10 ** (target_db / 20)
        
        # Normalize
        normalized = audio * (target_rms / rms)
        
        # Clip to prevent distortion
        normalized = np.clip(normalized, -1.0, 1.0)
        
        return normalized
    
    def trim_silence(
        self,
        audio: np.ndarray,
        threshold_db: float = -40.0,
        frame_length: int = 2048,
        hop_length: int = 512
    ) -> np.ndarray:
        """
        Trim silence from audio.
        
        Args:
            audio: Audio data
            threshold_db: Silence threshold in dB
            frame_length: Frame length for analysis
            hop_length: Hop length for analysis
            
        Returns:
            Trimmed audio
        """
        try:
            import librosa
            
            threshold = 10 ** (threshold_db / 20)
            trimmed, _ = librosa.effects.trim(
                audio,
                top_db=-20 * np.log10(threshold),
                frame_length=frame_length,
                hop_length=hop_length
            )
            
            return trimmed
            
        except Exception as e:
            logger.warning(f"Could not trim silence: {e}")
            return audio
    
    def resample(
        self,
        audio: np.ndarray,
        orig_sr: int,
        target_sr: int
    ) -> np.ndarray:
        """
        Resample audio to a different sample rate.
        
        Args:
            audio: Audio data
            orig_sr: Original sample rate
            target_sr: Target sample rate
            
        Returns:
            Resampled audio
        """
        if orig_sr == target_sr:
            return audio
        
        try:
            import librosa
            return librosa.resample(audio, orig_sr=orig_sr, target_sr=target_sr)
        except Exception as e:
            logger.warning(f"Could not resample audio: {e}")
            return audio
    
    def prepare_reference(
        self,
        audio_path: Union[str, Path],
        min_duration: float = 6.0,
        normalize: bool = True,
        trim_silence: bool = True
    ) -> Tuple[np.ndarray, int]:
        """
        Prepare reference audio for voice cloning.
        
        Args:
            audio_path: Path to reference audio
            min_duration: Minimum required duration
            normalize: Whether to normalize audio
            trim_silence: Whether to trim silence
            
        Returns:
            Tuple of (processed_audio, sample_rate)
            
        Raises:
            AudioTooShortError: If audio is too short
        """
        audio, sr = self.load_audio(audio_path)
        
        # Check duration
        duration = len(audio) / sr
        if duration < min_duration:
            raise AudioTooShortError(
                f"Reference audio too short: {duration:.1f}s (minimum: {min_duration}s)",
                {"duration": duration, "minimum": min_duration}
            )
        
        # Process
        if trim_silence:
            audio = self.trim_silence(audio)
        
        if normalize:
            audio = self.normalize(audio)
        
        logger.info(f"Prepared reference audio: {duration:.1f}s")
        return audio, sr