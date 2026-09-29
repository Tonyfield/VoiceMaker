#!/usr/bin/env python3
"""
IndexTTS2 Model Implementation Module
Handles IndexTTS2 model loading and synthesis
"""

import os
import sys
import time
from pathlib import Path

from .logger import logger
from .tts_model import TTSModel


class IndexTTS2Model(TTSModel):
    """IndexTTS2 Model Implementation"""
    
    def _initialize_model(self):
        """Initialize IndexTTS2 model"""
        try:
            from indextts import IndexTTS
            
            logger.info(f"📦 Loading IndexTTS2 model...")
            
            # Initialize IndexTTS model
            self.model = IndexTTS()
            
            # Load voice clone audio if provided
            self.voice_clone_audio = None
            if hasattr(self.args, 'voice_clone_audio') and self.args.voice_clone_audio:
                self._load_voice_clone()
            
            logger.success("🎉 IndexTTS2 model loaded successfully")
            
        except ImportError as e:
            logger.error(f"❌ Error: Required libraries not installed: {e}")
            logger.error("Please install: pip install indextts")
            sys.exit(1)
        except Exception as e:
            logger.error(f"❌ Error loading model: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    
    def _load_voice_clone(self):
        """Load voice clone reference audio"""
        try:
            audio_path = Path(self.args.voice_clone_audio)
            if not audio_path.exists():
                raise FileNotFoundError(f"Voice clone audio not found: {audio_path}")
            
            logger.info(f"🎵 Loading voice clone audio from: {audio_path}")
            self.voice_clone_audio = str(audio_path)
            logger.success("✅ Voice clone audio loaded successfully")
            
        except Exception as e:
            logger.warning(f"⚠️ Warning: Failed to load voice clone audio: {e}")
            self.voice_clone_audio = None
    
    def synthesize(self, text: str, output_path: str) -> bool:
        """Synthesize speech from text"""
        start_time = time.time()
        
        try:
            # Convert to Path object and normalize
            output_path = Path(output_path)
            output_path = output_path.resolve()  # Get absolute path
            
            # Determine output format
            if hasattr(self.args, 'output_format'):
                format = self.args.output_format
            else:
                format = "wav"
            
            # Determine language (default to Chinese)
            language = getattr(self.args, 'language', 'zh')
            
            # Get emotion parameter
            emotion = getattr(self.args, 'emotion', 'neutral')
            
            # Get speed parameter
            speed = getattr(self.args, 'speed', 1.0)
            
            # Calculate text statistics
            text_length = len(text)
            
            # Estimate token count (rough approximation: ~4 chars per token for Chinese)
            estimated_tokens = int(text_length / 4)
            
            logger.info(f"📝 Starting TTS synthesis...")
            logger.info(f"📊 Input text length: {text_length} characters")
            logger.info(f"🔢 Estimated tokens: ~{estimated_tokens}")
            logger.info(f"🌐 Language: {language}")
            logger.info(f"😊 Emotion: {emotion}")
            logger.info(f"⚡ Speed: {speed}x")
            logger.info(f"💾 Output format: {format}")
            
            # Build synthesis parameters
            params = {
                'text': text,
                'emotion': emotion,
                'speed': speed,
                'language': language
            }
            
            # Add voice reference if provided
            if self.voice_clone_audio:
                logger.info(f"🎙️ Using voice cloning...")
                logger.info(f"🎵 Reference audio: {self.voice_clone_audio}")
                params['voice_reference'] = self.voice_clone_audio
            else:
                logger.info(f"🎙️ Using default voice...")
            
            # Generate audio
            logger.info(f"🎵 Generating audio...")
            audio = self.model.synthesize(**params)
            
            # Create output file path with correct extension
            output_file = output_path.with_suffix(f'.{format}')
            
            # Ensure parent directory exists
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Convert to absolute path string
            output_file_str = str(output_file.absolute())
            
            # Save audio
            audio.save(output_file_str)
            
            # Calculate elapsed time
            elapsed_time = time.time() - start_time
            
            # Get audio file size
            file_size = os.path.getsize(output_file_str)
            
            # Display statistics
            logger.success("✅ Audio synthesis completed successfully!")
            logger.info(f"📁 Output file: {output_file}")
            logger.info(f"📊 File size: {file_size:,} bytes")
            logger.info(f"⏱️ Elapsed time: {elapsed_time:.2f} seconds")
            logger.info(f"📝 Input text length: {text_length} characters")
            logger.info(f"🔢 Estimated tokens: ~{estimated_tokens}")
            logger.info(f"⚡ Speed: {text_length / elapsed_time:.1f} chars/sec")
            
            return True
            
        except Exception as e:
            elapsed_time = time.time() - start_time
            logger.error(f"❌ Error during synthesis: {e}")
            logger.error(f"⏱️ Time elapsed before error: {elapsed_time:.2f} seconds")
            import traceback
            traceback.print_exc()
            return False