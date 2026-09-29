#!/usr/bin/env python3
"""
Qwen3-TTS Model Implementation Module
Handles Qwen3-TTS model loading and synthesis
"""

import os
import sys
from pathlib import Path
import numpy as np
import time

from .logger import logger
from .tts_model import TTSModel


class Qwen3TTSModel(TTSModel):
    """Qwen3-TTS Model Implementation"""
    
    def _initialize_model(self):
        """Initialize Qwen3-TTS model"""
        try:
            from qwen_tts import Qwen3TTSModel
            from modelscope import snapshot_download
            import os
            
            # Set HF mirror to use Chinese mirror by default
            os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
            logger.info(f"🌐 Using Hugging Face mirror: {os.environ['HF_ENDPOINT']}")
            
            logger.info(f"📦 Loading Qwen3-TTS model: {self.config['name']}")
            
            # Get model path from configuration
            model_path = self._get_model_path()
            
            # Try to find the model in the specified path
            actual_model_path = self._find_model_path(model_path)
            
            if actual_model_path:
                logger.info(f"✅ Using existing model at: {actual_model_path}")
                self.model = Qwen3TTSModel.from_pretrained(actual_model_path)
            else:
                logger.info(f"⬇️ Model not found at {model_path}, downloading from ModelScope...")
                
                # Download model using ModelScope to specified path
                model_name = self.config['name']
                
                # Create parent directory if it doesn't exist
                if model_path and os.path.dirname(model_path):
                    os.makedirs(os.path.dirname(model_path), exist_ok=True)
                
                actual_model_path = snapshot_download(
                    model_name,
                    cache_dir=model_path,
                    revision='master'
                )
                logger.info(f"✅ Model downloaded to: {actual_model_path}")
                
                # Initialize Qwen3-TTS model using from_pretrained with local path
                self.model = Qwen3TTSModel.from_pretrained(actual_model_path)
            
            # Load voice clone audio if provided
            self.voice_clone_audio = None
            if hasattr(self.args, 'voice_clone_audio') and self.args.voice_clone_audio:
                self._load_voice_clone()
            
            logger.success("🎉 Model loaded successfully")
            
        except ImportError as e:
            logger.error(f"❌ Error: Required libraries not installed: {e}")
            logger.error("Please install: pip install qwen-tts modelscope")
            sys.exit(1)
        except Exception as e:
            logger.error(f"❌ Error loading model: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    
    def _get_model_path(self) -> str:
        """Get model path from configuration or use default"""
        # Use configured model path if available
        if 'model_path' in self.config:
            return self.config['model_path']
        
        # Fallback to default path: D:\llm-models\<model-name>
        model_name = self.config['name'].replace('/', '\\')
        default_path = f"D:\\llm-models\\{model_name}"
        return default_path
    
    def _find_model_path(self, base_path: str) -> str:
        """Find the actual model path in the specified base directory"""
        if not os.path.exists(base_path):
            return None
        
        # If base_path is a file or directly contains config.json, return it
        if os.path.isfile(base_path):
            return None
        if os.path.exists(os.path.join(base_path, 'config.json')):
            return base_path
        
        # Search for model directories in subdirectories
        model_name = self.config['name'].split('/')[-1]  # Extract model name from "Qwen/Qwen3-TTS-12Hz-0.6B-Base"
        
        # Try to find the model in common locations
        for root, dirs, files in os.walk(base_path):
            # Check if this directory contains config.json
            if 'config.json' in files:
                # Check if directory name matches or is close to model name
                dir_name = os.path.basename(root)
                if model_name in dir_name or dir_name.replace('_', '-') in model_name or model_name.replace('-', '_') in dir_name:
                    return root
            
            # Limit search depth to avoid too much traversal
            if root.count(os.sep) - base_path.count(os.sep) > 3:
                dirs[:] = []  # Don't recurse further
        
        return None
    
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
            language = getattr(self.args, 'language', 'Chinese')
            
            # Calculate text statistics
            text_length = len(text)
            
            # Estimate token count (rough approximation: ~1.3 chars per token for Chinese)
            estimated_tokens = int(text_length / 1.3)
            
            logger.info(f"📝 Starting TTS synthesis...")
            logger.info(f"📊 Input text length: {text_length} characters")
            logger.info(f"🔢 Estimated tokens: ~{estimated_tokens}")
            logger.info(f"🌐 Language: {language}")
            logger.info(f"💾 Output format: {format}")
            
            # Check if voice clone audio is provided (required for Base model)
            if self.config.get('requires_reference_audio', False) and not self.voice_clone_audio:
                logger.error("❌ Error: Base model requires voice clone audio reference.")
                logger.error("Please provide --voice-clone-audio parameter with a 3-second audio sample.")
                logger.error("Or use CustomVoice model for direct TTS without voice cloning.")
                return False
            
            # Determine which generation method to use
            if self.voice_clone_audio and self.config.get('supports_voice_cloning', False):
                # Voice cloning mode
                logger.info(f"🎙️ Generating audio with voice cloning...")
                logger.info(f"🎵 Reference audio: {self.voice_clone_audio}")
                
                wavs, sr = self.model.generate_voice_clone(
                    text=text,
                    ref_audio=self.voice_clone_audio,
                    x_vector_only_mode=True, 
                    language=language
                )
            else:
                # CustomVoice mode (preset speakers)
                speaker = getattr(self.args, 'speaker', 'aiden')
                logger.info(f"🎙️ Generating audio with CustomVoice...")
                logger.info(f"👤 Speaker: {speaker}")
                
                wavs, sr = self.model.generate_custom_voice(
                    text=text,
                    language=language,
                    speaker=speaker
                )
            
            # Save audio
            import soundfile as sf
            
            # Create output file path with correct extension
            output_file = output_path.with_suffix(f'.{format}')
            
            # Ensure parent directory exists
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Convert to absolute path string
            output_file_str = str(output_file.absolute())
            
            # Convert wavs to numpy array if needed
            if not isinstance(wavs, np.ndarray):
                if hasattr(wavs, 'cpu'):
                    wavs = wavs.cpu().numpy()
                else:
                    wavs = np.array(wavs)
            
            # Flatten if needed
            if wavs.ndim > 1:
                wavs = wavs.squeeze()
            
            # Ensure wavs is 1D array
            if wavs.ndim == 0:
                wavs = wavs.reshape(1)
            
            # Save using soundfile with explicit parameters
            try:
                sf.write(output_file_str, wavs, sr, format=format.upper())
            except Exception as e:
                logger.error(f"❌ Error with soundfile: {e}")
                # Try alternative method
                import scipy.io.wavfile as wavfile
                if format.lower() == 'wav':
                    wavfile.write(output_file_str, sr, wavs)
                else:
                    raise e
            
            # Calculate elapsed time
            elapsed_time = time.time() - start_time
            
            # Calculate audio duration
            audio_duration = len(wavs) / sr
            
            # Calculate real-time factor (RTF)
            rtf = elapsed_time / audio_duration if audio_duration > 0 else 0
            
            # Display statistics
            logger.success("✅ Audio synthesis completed successfully!")
            logger.info(f"📁 Output file: {output_file}")
            logger.info(f"🎧 Sample rate: {sr} Hz")
            logger.info(f"📊 Audio shape: {wavs.shape}")
            logger.info(f"⏱️ Audio duration: {audio_duration:.2f} seconds")
            logger.info(f"⏱️ Elapsed time: {elapsed_time:.2f} seconds")
            logger.info(f"📈 Real-time factor (RTF): {rtf:.3f}")
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