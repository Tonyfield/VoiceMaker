"""
Audio utility functions for TTS Voice Cloning.
"""
from pathlib import Path
from typing import List, Optional, Tuple, Union

import numpy as np
from loguru import logger

from src.exceptions import AudioProcessingError, InvalidAudioFormatError


# Supported audio formats
SUPPORTED_FORMATS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac"}


def is_supported_format(file_path: Union[str, Path]) -> bool:
    """
    Check if a file has a supported audio format.
    
    Args:
        file_path: Path to the file
        
    Returns:
        True if format is supported
    """
    path = Path(file_path)
    return path.suffix.lower() in SUPPORTED_FORMATS


def get_audio_info(audio_path: Union[str, Path]) -> dict:
    """
    Get information about an audio file.
    
    Args:
        audio_path: Path to audio file
        
    Returns:
        Dictionary with audio information
        
    Raises:
        AudioProcessingError: If unable to read audio info
    """
    try:
        import librosa
        
        path = Path(audio_path)
        duration = librosa.get_duration(path=str(path))
        
        # Get sample rate
        y, sr = librosa.load(str(path), sr=None, mono=False)
        
        channels = 1 if y.ndim == 1 else y.shape[0]
        
        return {
            "path": str(path),
            "duration": duration,
            "sample_rate": sr,
            "channels": channels,
            "format": path.suffix.lower(),
            "size_bytes": path.stat().st_size
        }
        
    except Exception as e:
        raise AudioProcessingError(
            f"Failed to get audio info: {e}",
            {"path": str(audio_path)}
        )


def convert_audio(
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    target_format: str = "wav",
    sample_rate: int = 24000,
    normalize: bool = True
) -> Path:
    """
    Convert audio to a different format.
    
    Args:
        input_path: Input audio file path
        output_path: Output audio file path
        target_format: Target format (wav, mp3, etc.)
        sample_rate: Target sample rate
        normalize: Whether to normalize audio
        
    Returns:
        Path to converted file
        
    Raises:
        AudioProcessingError: If conversion fails
    """
    try:
        import librosa
        import soundfile as sf
        
        # Load audio
        y, sr = librosa.load(str(input_path), sr=sample_rate, mono=True)
        
        # Normalize if requested
        if normalize:
            y = normalize_audio(y)
        
        # Ensure output path has correct extension
        output = Path(output_path)
        if not output.suffix:
            output = output.with_suffix(f".{target_format}")
        
        # Save
        output.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(output), y, sample_rate)
        
        logger.info(f"Converted audio: {input_path} -> {output}")
        return output
        
    except Exception as e:
        raise AudioProcessingError(
            f"Failed to convert audio: {e}",
            {"input": str(input_path), "output": str(output_path)}
        )


def normalize_audio(
    audio: np.ndarray,
    target_db: float = -3.0
) -> np.ndarray:
    """
    Normalize audio to target dB level.
    
    Args:
        audio: Audio data as numpy array
        target_db: Target dB level
        
    Returns:
        Normalized audio
    """
    rms = np.sqrt(np.mean(audio ** 2))
    
    if rms == 0:
        return audio
    
    target_rms = 10 ** (target_db / 20)
    normalized = audio * (target_rms / rms)
    
    return np.clip(normalized, -1.0, 1.0)


def split_audio(
    audio_path: Union[str, Path],
    segment_duration: float = 30.0,
    output_dir: Optional[Union[str, Path]] = None
) -> List[Path]:
    """
    Split audio into segments.
    
    Args:
        audio_path: Path to audio file
        segment_duration: Duration of each segment in seconds
        output_dir: Directory for output files (uses temp if not specified)
        
    Returns:
        List of paths to segment files
        
    Raises:
        AudioProcessingError: If splitting fails
    """
    try:
        import librosa
        import soundfile as sf
        import tempfile
        
        path = Path(audio_path)
        
        # Load audio
        y, sr = librosa.load(str(path), sr=None, mono=True)
        total_duration = len(y) / sr
        
        # Calculate number of segments
        num_segments = int(np.ceil(total_duration / segment_duration))
        
        # Create output directory
        if output_dir:
            out_dir = Path(output_dir)
        else:
            out_dir = Path(tempfile.mkdtemp())
        out_dir.mkdir(parents=True, exist_ok=True)
        
        segments = []
        samples_per_segment = int(segment_duration * sr)
        
        for i in range(num_segments):
            start = i * samples_per_segment
            end = min((i + 1) * samples_per_segment, len(y))
            
            segment = y[start:end]
            segment_path = out_dir / f"{path.stem}_part{i+1}.wav"
            
            sf.write(str(segment_path), segment, sr)
            segments.append(segment_path)
        
        logger.info(f"Split audio into {len(segments)} segments")
        return segments
        
    except Exception as e:
        raise AudioProcessingError(
            f"Failed to split audio: {e}",
            {"path": str(audio_path)}
        )


def concatenate_audio(
    audio_paths: List[Union[str, Path]],
    output_path: Union[str, Path],
    sample_rate: int = 24000,
    silence_duration: float = 0.5
) -> Path:
    """
    Concatenate multiple audio files.
    
    Args:
        audio_paths: List of audio file paths
        output_path: Output file path
        sample_rate: Target sample rate
        silence_duration: Duration of silence between files (seconds)
        
    Returns:
        Path to concatenated file
        
    Raises:
        AudioProcessingError: If concatenation fails
    """
    try:
        import librosa
        import soundfile as sf
        
        segments = []
        silence = np.zeros(int(silence_duration * sample_rate))
        
        for path in audio_paths:
            y, _ = librosa.load(str(path), sr=sample_rate, mono=True)
            segments.extend([y, silence])
        
        # Remove trailing silence
        if segments:
            segments = segments[:-1]
        
        concatenated = np.concatenate(segments)
        
        # Save
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(output), concatenated, sample_rate)
        
        logger.info(f"Concatenated {len(audio_paths)} audio files")
        return output
        
    except Exception as e:
        raise AudioProcessingError(
            f"Failed to concatenate audio: {e}",
            {"paths": [str(p) for p in audio_paths]}
        )


def validate_reference_audio(
    audio_path: Union[str, Path],
    min_duration: float = 6.0,
    max_duration: Optional[float] = None
) -> Tuple[bool, str]:
    """
    Validate a reference audio file for voice cloning.
    
    Args:
        audio_path: Path to audio file
        min_duration: Minimum required duration
        max_duration: Maximum allowed duration (None for no limit)
        
    Returns:
        Tuple of (is_valid, message)
    """
    path = Path(audio_path)
    
    # Check file exists
    if not path.exists():
        return False, f"File not found: {audio_path}"
    
    # Check format
    if not is_supported_format(path):
        return False, f"Unsupported format: {path.suffix}"
    
    try:
        info = get_audio_info(path)
        duration = info["duration"]
        
        if duration < min_duration:
            return False, f"Audio too short: {duration:.1f}s (minimum: {min_duration}s)"
        
        if max_duration and duration > max_duration:
            return False, f"Audio too long: {duration:.1f}s (maximum: {max_duration}s)"
        
        return True, f"Valid audio: {duration:.1f}s, {info['sample_rate']}Hz"
        
    except Exception as e:
        return False, f"Error validating audio: {e}"