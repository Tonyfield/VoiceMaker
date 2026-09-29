"""
Enhanced text-to-speech conversion module that processes segmented XHTML content.
Converts each text segment into audio files with matching filenames.
"""
import os
from pathlib import Path
from typing import Dict, List, Optional, Union

from loguru import logger

from src.config import config
from src.models.base import BaseTTSModel
from src.models.xtts import XTTSModel
from src.utils.xhtml_segmenter import XHTMLSegmenter
from src.voice.processor import AudioProcessor
from src.voice.profile import VoiceProfileManager

# 全局变量用于跟踪中断状态
try:
    from tools.book_to_audio import interrupted
except ImportError:
    # 如果无法导入，则定义本地变量
    interrupted = False


class TTSConverter:
    """
    Enhanced TTS converter that processes segmented XHTML content.
    
    Features:
    - Accepts segmented output from XHTMLSegmenter
    - Processes each segment individually
    - Generates audio files with matching segment IDs
    - Supports voice cloning with reference audio
    - Handles batch processing with progress tracking
    - Supports resuming interrupted conversions
    """
    
    def __init__(
        self,
        model: Optional[BaseTTSModel] = None,
        output_dir: str = "audio_output",
        reference_audio: Optional[str] = None,
        voice_profile: Optional[str] = None,
        language: str = "auto",
        output_format: str = "mp3"
    ):
        """
        Initialize TTS converter.
        
        Args:
            model: TTS model to use (creates XTTSModel if not provided)
            output_dir: Directory to save audio files
            reference_audio: Path to reference audio for voice cloning
            voice_profile: Name of voice profile for voice cloning
            language: Language code for synthesis
            output_format: Output audio format (mp3, wav, etc.)
        """
        # Directly use XTTSModel for better control
        self.model = model or XTTSModel()
        self.output_dir = Path(output_dir)
        self.reference_audio = reference_audio
        self.voice_profile = voice_profile
        self.language = language
        self.output_format = output_format.lower()
        self.processed_segments = set()
        
        # Initialize audio processor for reference audio handling
        self.audio_processor = AudioProcessor()
        
        # Initialize voice profile manager
        self.profile_manager = VoiceProfileManager()
        
        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Check reference audio file
        if self.reference_audio and not os.path.exists(self.reference_audio):
            logger.error(f"参考音频文件不存在: {self.reference_audio}")
            raise FileNotFoundError(f"参考音频文件不存在: {self.reference_audio}")
        
        # Load the model
        if not self.model.is_loaded:
            self.model.load_model()
    
    def process_segments(
        self,
        segments: List[Dict],
        resume: bool = True,
        skip_existing: bool = True,
        continue_on_error: bool = False
    ) -> List[str]:
        """
        Process a list of text segments and convert them to audio.
        
        Args:
            segments: List of segment dictionaries from XHTMLSegmenter
            resume: Whether to resume from where we left off
            skip_existing: Whether to skip segments that already have audio files
            
        Returns:
            List of paths to generated audio files
        """
        logger.info(f"Processing {len(segments)} segments")
        
        # Check for existing files if resuming
        if resume or skip_existing:
            self._check_existing_files()
        
        audio_files = []
        
        for i, segment in enumerate(segments):
            # 检查是否被中断
            if interrupted:
                logger.info("检测到中断信号，停止处理")
                break
            segment_id = segment['segment_id']
            
            # Skip if already processed
            if skip_existing and segment_id in self.processed_segments:
                logger.debug(f"Skipping already processed segment: {segment_id}")
                continue
            
            try:
                # Generate audio file path (always use .wav for intermediate file)
                wav_path = self.output_dir / f"{segment_id}.wav"
                
                # Generate final output path based on format
                if self.output_format == "mp3":
                    audio_path = self.output_dir / f"{segment_id}.mp3"
                else:
                    audio_path = wav_path
                
                # Convert text to speech using XTTSModel with proper audio processing
                if self.reference_audio:
                    # Prepare reference audio using AudioProcessor
                    self.audio_processor.prepare_reference(self.reference_audio)
                    wav_path_str = self.model.synthesize_with_voice(
                        text=segment['content'],
                        reference_audio=self.reference_audio,
                        output_path=str(wav_path),
                        language=self.language or self._detect_language(segment['content'])
                    )
                    wav_path = Path(wav_path_str)
                elif self.voice_profile:
                    # Load voice profile
                    profile = self.profile_manager.load(self.voice_profile)
                    if not profile.reference_audio:
                        raise ValueError(f"Voice profile '{self.voice_profile}' has no reference audio")
                    
                    # Prepare reference audio using AudioProcessor
                    self.audio_processor.prepare_reference(profile.reference_audio)
                    
                    wav_path_str = self.model.synthesize_with_voice(
                        text=segment['content'],
                        reference_audio=profile.reference_audio,
                        output_path=str(wav_path),
                        language=profile.language or self.language or self._detect_language(segment['content'])
                    )
                    wav_path = Path(wav_path_str)
                else:
                    # Generate a temporary reference audio if none provided
                    import numpy as np
                    import soundfile as sf
                    
                    # Create a temporary reference audio file
                    temp_ref = wav_path.parent / "temp_reference.wav"
                    
                    # Generate a minimal sine wave as reference
                    sample_rate = 22050
                    duration = 3.0  # 3 seconds (XTTS requires at least 3 seconds)
                    frequency = 440  # A4 note
                    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
                    sine_wave = 0.3 * np.sin(2 * np.pi * frequency * t)
                    
                    # Save the temporary reference audio
                    sf.write(str(temp_ref), sine_wave, sample_rate)
                    
                    logger.info(f"Using generated reference audio: {temp_ref}")
                    
                    # Use the temporary reference audio
                    wav_path_str = self.model.synthesize_with_voice(
                        text=segment['content'],
                        reference_audio=str(temp_ref),
                        language=self.language or self._detect_language(segment['content']),
                        output_path=str(wav_path)
                    )
                    wav_path = Path(wav_path_str)
                    
                    # Clean up the temporary reference audio
                    try:
                        temp_ref.unlink()
                    except:
                        pass
                
                # Convert to MP3 if needed
                if self.output_format == "mp3" and wav_path != audio_path:
                    self._convert_to_mp3(wav_path, audio_path)
                    # Remove the temporary WAV file
                    try:
                        wav_path.unlink()
                    except:
                        pass
                
                audio_files.append(audio_path)
                self.processed_segments.add(segment_id)
                
                # Log progress
                if (i + 1) % 10 == 0 or i == len(segments) - 1:
                    logger.info(f"Processed {i + 1}/{len(segments)} segments")
                
            except Exception as e:
                logger.error(f"Error processing segment {segment_id}: {e}")
                logger.error(f"Segment content: {segment['content'][:100]}...")
                logger.error("Processing stopped due to error. Please fix the issue and retry.")
                raise e
        
        logger.success(f"Generated {len(audio_files)} audio files")
        return audio_files
    
    def process_segment_file(
        self,
        segment_file: str,
        resume: bool = True,
        skip_existing: bool = True
    ) -> List[str]:
        """
        Process segments from a JSON file generated by XHTMLSegmenter.
        
        Args:
            segment_file: Path to JSON file with segments
            resume: Whether to resume from where we left off
            skip_existing: Whether to skip segments that already have audio files
            
        Returns:
            List of paths to generated audio files
        """
        import json
        
        logger.info(f"Loading segments from {segment_file}")
        
        with open(segment_file, 'r', encoding='utf-8') as f:
            segments = json.load(f)
        
        return self.process_segments(segments, resume, skip_existing)
    
    def process_book(
        self,
        book_dir: str,
        segment_file: Optional[str] = None,
        resume: bool = True,
        skip_existing: bool = True
    ) -> List[str]:
        """
        Process an entire book directory and convert to audio.
        
        Args:
            book_dir: Path to book directory with OEBPS/Text
            segment_file: Optional path to save/load segments file
            resume: Whether to resume from where we left off
            skip_existing: Whether to skip segments that already have audio files
            
        Returns:
            List of paths to generated audio files
        """
        # Create segmenter
        segmenter = XHTMLSegmenter(book_dir)
        
        # Process all files
        segments = segmenter.process_all_files()
        
        # Save segments if path provided
        if segment_file:
            segmenter.save_to_json(segment_file)
        
        # Convert to audio
        return self.process_segments(segments, resume, skip_existing)
    
    def _check_existing_files(self) -> None:
        """
        Check for existing audio files to support resuming.
        """
        # Check for both WAV and MP3 files based on output format
        pattern = f"*.{self.output_format}"
        
        for audio_file in self.output_dir.glob(pattern):
            # Extract segment ID from filename
            segment_id = audio_file.stem
            self.processed_segments.add(segment_id)
        
        if self.processed_segments:
            logger.info(f"Found {len(self.processed_segments)} existing audio files")
    
    def _detect_language(self, text: str) -> str:
        """
        Detect language of text for TTS synthesis.
        
        Args:
            text: Input text
            
        Returns:
            Detected language code
        """
        try:
            from langdetect import detect
            detected = detect(text)
            
            # Map to XTTS language codes
            lang_map = {
                "zh-cn": "zh-cn",
                "zh-tw": "zh-cn",
                "zh": "zh-cn",
                "ja": "ja",
                "ko": "ko",
                "en": "en",
                "fr": "fr",
                "de": "de",
                "es": "es",
                "it": "it",
                "pt": "pt",
                "ru": "ru",
                "ar": "ar",
                "hi": "hi",
                "nl": "nl",
                "pl": "pl",
                "tr": "tr",
                "cs": "cs",
                "hu": "hu"
            }
            
            return lang_map.get(detected, "zh-cn")  # Default to Chinese for this book
            
        except Exception:
            # Fallback: check for Chinese characters
            chinese_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
            total_alpha = sum(1 for c in text if c.isalpha())
            
            if total_alpha > 0 and chinese_chars / total_alpha > 0.3:
                return "zh-cn"
            
            return "zh-cn"  # Default to Chinese for this book
    
    def _convert_to_mp3(self, wav_path, mp3_path) -> None:
        """
        Convert WAV file to MP3 format.
        
        Args:
            wav_path: Path to the input WAV file (Path object or string)
            mp3_path: Path to save the output MP3 file (Path object or string)
        """
        # Ensure we have Path objects
        wav_path = Path(wav_path)
        mp3_path = Path(mp3_path)
        
        try:
            from pydub import AudioSegment
            
            # Load the WAV file
            audio = AudioSegment.from_wav(str(wav_path))
            
            # Export as MP3
            audio.export(str(mp3_path), format="mp3", bitrate="128k")
            
            logger.debug(f"Converted {wav_path.name} to {mp3_path.name}")
        except ImportError:
            logger.error("pydub not installed. Please install it with: pip install pydub")
            # If pydub is not available, just copy the file
            import shutil
            shutil.copy2(str(wav_path), str(mp3_path))
        except Exception as e:
            logger.error(f"Failed to convert {wav_path.name} to MP3: {e}")
            # If conversion fails, just copy the file
            import shutil
            shutil.copy2(str(wav_path), str(mp3_path))
    
    def get_progress(self) -> Dict[str, Union[int, float]]:
        """
        Get progress information for the conversion process.
        
        Returns:
            Dictionary with progress statistics
        """
        total_files = len(list(self.output_dir.glob("*.wav")))
        return {
            "processed_segments": len(self.processed_segments),
            "total_audio_files": total_files,
            "output_directory": str(self.output_dir)
        }