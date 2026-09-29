#!/usr/bin/env python3
"""
VoxCPM2 Model Implementation Module
Handles VoxCPM2 model loading and synthesis
"""

import os
import sys
import time
from pathlib import Path
import numpy as np

from .logger import logger
from .tts_model import TTSModel


class VoxCPM2Model(TTSModel):
    """VoxCPM2 Model Implementation"""
    
    def _initialize_model(self):
        """Initialize VoxCPM2 model"""
        try:
            # Check and install voxcpm package if not installed
            self._ensure_voxcpm_installed()
            
            from voxcpm import VoxCPM
            
            logger.info(f"📦 Loading VoxCPM2 model...")
            
            # Get model path from configuration
            model_path = self._get_model_path()
            
            # Ensure model files are downloaded
            self._ensure_model_downloaded(model_path)
            
            # Load model
            logger.info(f"📦 Loading VoxCPM2 model...")
            logger.info(f"⏳ This may take 1-3 minutes on first run, please wait...")
            
            # Try different initialization methods based on API version
            try:
                # Try with positional argument (voxcpm_model_path)
                logger.info(f"⏳ Initializing VoxCPM model from {model_path} (this may take a while)...")
                self.model = VoxCPM.from_pretrained(model_path)
                logger.info(f"✅ Initialized with model_path: {model_path}")

            except TypeError:
                # Try with no parameters (will use default path)
                logger.error(f"❌ Failed to initialize VoxCPM model on {model_path}")
                sys.exit(1)
    
            # Load voice clone audio if provided
            self.voice_clone_audio = None
            if hasattr(self.args, 'voice_clone_audio') and self.args.voice_clone_audio:
                self._load_voice_clone()
            
            logger.success("🎉 VoxCPM2 model loaded successfully")
            
        except ImportError as e:
            logger.error(f"❌ Error: Required libraries not installed: {e}")
            logger.error("Please install: pip install voxcpm")
            logger.error("GitHub: https://github.com/OpenBMB/VoxCPM")
            sys.exit(1)
        except Exception as e:
            logger.error(f"❌ Error loading model: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    
    def _ensure_voxcpm_installed(self):
        """Ensure voxcpm package is installed"""
        try:
            import voxcpm
            logger.info(f"✅ voxcpm package is already installed")
        except ImportError:
            logger.warning(f"⚠️  voxcpm package not found")
            logger.info(f"📦 Installing voxcpm package...")
            
            try:
                import subprocess
                subprocess.check_call([
                    sys.executable, "-m", "pip", "install", "voxcpm"
                ])
                logger.success(f"✅ voxcpm package installed successfully")
            except subprocess.CalledProcessError as e:
                logger.error(f"❌ Failed to install voxcpm: {e}")
                logger.error(f"Please install manually: pip install voxcpm")
                sys.exit(1)
    
    def _ensure_model_downloaded(self, model_path: str):
        """Ensure VoxCPM2 model files are downloaded"""
        import os
        
        # Check if model directory exists
        if not os.path.exists(model_path):
            logger.warning(f"⚠️  Model directory not found: {model_path}")
            logger.info(f"📦 Downloading VoxCPM2 model from ModelScope...")
            
            try:
                # Create model directory
                os.makedirs(model_path, exist_ok=True)
                
                # Download model using ModelScope
                try:
                    from modelscope import snapshot_download
                    
                    logger.info(f"🌐 Downloading from ModelScope: OpenBMB/VoxCPM2")
                    logger.info(f"📁 Target directory: {model_path}")
                    
                    # Download to parent directory to avoid subdirectory issues
                    parent_dir = os.path.dirname(model_path)
                    downloaded_path = snapshot_download(
                        'OpenBMB/VoxCPM2',
                        cache_dir=parent_dir,
                        revision='master'
                    )
                    
                    logger.success(f"✅ VoxCPM2 model downloaded successfully")
                    logger.info(f"📁 Model location: {downloaded_path}")
                    
                    # Find the actual model directory (may be in subdirectory)
                    actual_model_path = self._find_actual_model_path(model_path)
                    if actual_model_path != model_path:
                        logger.info(f"📁 Actual model path: {actual_model_path}")
                    
                except ImportError:
                    logger.warning(f"⚠️  modelscope not installed")
                    logger.info(f"📦 Installing modelscope...")
                    
                    import subprocess
                    subprocess.check_call([
                        sys.executable, "-m", "pip", "install", "modelscope"
                    ])
                    
                    logger.info(f"🌐 Downloading from ModelScope: OpenBMB/VoxCPM2")
                    from modelscope import snapshot_download
                    
                    parent_dir = os.path.dirname(model_path)
                    downloaded_path = snapshot_download(
                        'OpenBMB/VoxCPM2',
                        cache_dir=parent_dir,
                        revision='master'
                    )
                    
                    logger.success(f"✅ VoxCPM2 model downloaded successfully")
                    logger.info(f"📁 Model location: {downloaded_path}")
                    
                    # Find the actual model directory
                    actual_model_path = self._find_actual_model_path(model_path)
                    if actual_model_path != model_path:
                        logger.info(f"📁 Actual model path: {actual_model_path}")
                    
            except Exception as e:
                logger.error(f"❌ Failed to download VoxCPM2 model: {e}")
                logger.error(f"Please download manually:")
                logger.error(f"  1. Visit ModelScope: https://modelscope.cn/models/OpenBMB/VoxCPM2")
                logger.error(f"  2. Download all files to: {model_path}")
                logger.error(f"  3. Or run: git clone https://www.modelscope.cn/OpenBMB/VoxCPM2.git {model_path}")
                sys.exit(1)
        else:
            # Check if config.json exists
            config_path = os.path.join(model_path, "config.json")
            if not os.path.exists(config_path):
                logger.warning(f"⚠️  Model files incomplete: {config_path} not found")
                logger.info(f"📦 Re-downloading VoxCPM2 model from ModelScope...")
                
                try:
                    from modelscope import snapshot_download
                    
                    logger.info(f"🌐 Downloading from ModelScope: OpenBMB/VoxCPM2")
                    parent_dir = os.path.dirname(model_path)
                    downloaded_path = snapshot_download(
                        'OpenBMB/VoxCPM2',
                        cache_dir=parent_dir,
                        revision='master'
                    )
                    
                    logger.success(f"✅ VoxCPM2 model downloaded successfully")
                    logger.info(f"📁 Model location: {downloaded_path}")
                    
                except Exception as e:
                    logger.error(f"❌ Failed to download VoxCPM2 model: {e}")
                    logger.error(f"Please download manually:")
                    logger.error(f"  1. Visit ModelScope: https://modelscope.cn/models/OpenBMB/VoxCPM2")
                    logger.error(f"  2. Download all files to: {model_path}")
                    sys.exit(1)
            else:
                logger.info(f"✅ VoxCPM2 model files found at {model_path}")
    
    def _find_actual_model_path(self, base_path: str) -> str:
        """Find the actual model path (may be in subdirectory)"""
        import os
        
        # Check possible paths
        possible_paths = [
            base_path,
            os.path.join(base_path, "OpenBMB", "VoxCPM2"),
            os.path.join(base_path, "VoxCPM2"),
        ]
        
        for path in possible_paths:
            if os.path.exists(os.path.join(path, "config.json")):
                return path
        
        return base_path
    
    def _get_model_path(self) -> str:
        """Get model path from configuration or use default"""
        # Use configured model path if available
        if 'model_path' in self.config:
            base_path = self.config['model_path']
        else:
            # Fallback to default path: D:\llm-models\VoxCPM2
            base_path = "D:\\llm-models\\VoxCPM2"
        
        # Check if the actual model files are in a subdirectory
        # ModelScope downloads to: D:\llm-models\OpenBMB\VoxCPM2
        import os
        
        # First, try to find config.json in the base path or subdirectories
        possible_paths = [
            base_path,
            os.path.join(base_path, "OpenBMB", "VoxCPM2"),
            os.path.join(base_path, "VoxCPM2"),
        ]
        
        for path in possible_paths:
            if os.path.exists(os.path.join(path, "config.json")):
                logger.info(f"✅ Found model files at: {path}")
                return path
        
        # If not found, return base path (will trigger download)
        return base_path
    
    def _is_cuda_available(self) -> bool:
        """Check if CUDA is available"""
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False
    
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
            output_path = output_path.resolve()
            
            # Determine output format
            if hasattr(self.args, 'output_format'):
                format = self.args.output_format
            else:
                format = "wav"
            
            # # Determine language (default to Chinese)
            # language = getattr(self.args, 'language', 'zh')
            
            # # Get emotion parameter
            # emotion = getattr(self.args, 'emotion', 'neutral')
            
            # # Get speed parameter
            # speed = getattr(self.args, 'speed', 1.0)
            
            # # Get pitch parameter
            # pitch = getattr(self.args, 'pitch', 1.0)
            
            # # Get energy parameter
            # energy = getattr(self.args, 'energy', 1.0)
            
            # # Get brightness parameter
            # brightness = getattr(self.args, 'brightness', 1.0)
            
            # # Get dialect parameter
            # dialect = getattr(self.args, 'dialect', None)
            
            # Calculate text statistics
            text_length = len(text)
            
            # Estimate token count (VoxCPM2 is tokenizer-free, so rough approximation)
            estimated_tokens = int(text_length / 2)
            
            logger.info(f"📝 Starting TTS synthesis...")
            logger.info(f"📊 Input text length: {text_length} characters")
            logger.info(f"🔢 Estimated tokens: ~{estimated_tokens}")
            # logger.info(f"🌐 Language: {language}")
            # logger.info(f"😊 Emotion: {emotion}")
            # logger.info(f"⚡ Speed: {speed}x")
            # logger.info(f"🎵 Pitch: {pitch}x")
            # logger.info(f"⚡ Energy: {energy}x")
            # logger.info(f"💡 Brightness: {brightness}x")
            # if dialect:
            #     logger.info(f"🗣️ Dialect: {dialect}")
            logger.info(f"💾 Output format: {format}")
            
            # Try different synthesis methods based on API
            audio = None
            sample_rate = 48000  # Default sample rate
            
            # Method 1: Try with all parameters
            try:
                params = {'text': text}
                if self.voice_clone_audio:
                    params['reference_wav_path'] = self.voice_clone_audio
                # if dialect:
                #     params['dialect'] = dialect
                
                voice_params = {}
                if pitch != 1.0:
                    voice_params['pitch'] = pitch
                if speed != 1.0:
                    voice_params['speed'] = speed
                if energy != 1.0:
                    voice_params['energy'] = energy
                if brightness != 1.0:
                    voice_params['brightness'] = brightness
                
                # if voice_params:
                #     params['voice_params'] = voice_params
                
                logger.info(f"🎵 Generating audio with full parameters...")
                audio = self.model.generate(**params)
                logger.info(f"✅ Full parameter synthesis successful")
            except Exception as e1:
                logger.warning(f"⚠️ Full parameter synthesis failed: {e1}")
                
                # Method 2: Try with basic parameters only
                try:
                    params = {'text': text}
                    if self.voice_clone_audio:
                        params['reference_wav_path'] = self.voice_clone_audio
                    
                    logger.info(f"🎵 Generating audio with basic parameters...")
                    audio = self.model.generate(**params)
                    logger.info(f"✅ Basic parameter synthesis successful")
                except Exception as e2:
                    logger.error(f"❌ Basic parameter synthesis failed: {e2}")
                    raise e2
            
            # Create output file path with correct extension
            output_file = output_path.with_suffix(f'.{format}')
            
            # Ensure parent directory exists
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Convert to absolute path string
            output_file_str = str(output_file.absolute())
            
            # Save audio
            import soundfile as sf
            
            # Convert to numpy array if needed
            if not isinstance(audio, np.ndarray):
                if hasattr(audio, 'cpu'):
                    audio = audio.cpu().numpy()
                elif hasattr(audio, 'numpy'):
                    audio = audio.numpy()
                else:
                    audio = np.array(audio)
            
            # Flatten if needed
            if audio.ndim > 1:
                audio = audio.squeeze()
            
            # Ensure audio is 1D array
            if audio.ndim == 0:
                audio = audio.reshape(1)
            
            # Get sample rate from audio or model or use default
            if hasattr(audio, 'sample_rate'):
                sample_rate = audio.sample_rate
            elif hasattr(self.model, 'sample_rate'):
                sample_rate = self.model.sample_rate
            else:
                sample_rate = 48000  # VoxCPM2 default
            
            # Save using soundfile
            sf.write(output_file_str, audio, sample_rate)
            
            # Calculate elapsed time
            elapsed_time = time.time() - start_time
            
            # Calculate audio duration
            audio_duration = len(audio) / sample_rate
            
            # Calculate real-time factor (RTF)
            rtf = elapsed_time / audio_duration if audio_duration > 0 else 0
            
            # Get audio file size
            file_size = os.path.getsize(output_file_str)
            
            # Display statistics
            logger.success("✅ Audio synthesis completed successfully!")
            logger.info(f"📁 Output file: {output_file}")
            logger.info(f"🎧 Sample rate: {sample_rate} Hz")
            logger.info(f"📊 Audio shape: {audio.shape}")
            logger.info(f"📊 File size: {file_size:,} bytes")
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