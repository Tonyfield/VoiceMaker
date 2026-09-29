#!/usr/bin/env python3
"""
TTS Factory Module
Factory for creating TTS model instances
"""

import argparse
from typing import Dict

from .tts_model import TTSModel


class TTSFactory:
    """Factory for creating TTS model instances"""
    
    @staticmethod
    def create_model(config: Dict, args: argparse.Namespace) -> TTSModel:
        """Create TTS model based on framework"""
        framework = config.get('framework', 'unknown')
        
        if framework == 'qwen3-tts':
            from .qwen3_tts_model import Qwen3TTSModel
            return Qwen3TTSModel(config, args)
        elif framework == 'indextts2':
            from .indextts2_model import IndexTTS2Model
            return IndexTTS2Model(config, args)
        elif framework == 'voxcpm2':
            from .voxcpm2_model import VoxCPM2Model
            return VoxCPM2Model(config, args)
        else:
            raise ValueError(f"Unsupported framework: {framework}")