#!/usr/bin/env python3
"""
TTS Profile Configuration Module
Handles loading and management of TTS model profiles from YAML files
"""

import yaml
from typing import Dict, List, Optional


class TTSProfile:
    """TTS Model Profile Configuration"""
    
    def __init__(self, profile_path: str):
        self.profile_path = profile_path
        self.profiles = self._load_profile()
    
    def _load_profile(self) -> Dict:
        """Load TTS profiles from YAML file"""
        with open(self.profile_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    def get_model_config(self, model_name: str) -> Dict:
        """Get configuration for specific model"""
        if model_name not in self.profiles['models']:
            available = ', '.join(self.profiles['models'].keys())
            raise ValueError(f"Model '{model_name}' not found. Available models: {available}")
        return self.profiles['models'][model_name]
    
    def list_models(self) -> List[str]:
        """List all available models"""
        return list(self.profiles['models'].keys())