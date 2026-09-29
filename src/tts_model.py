#!/usr/bin/env python3
"""
TTS Model Base Class Module
Defines the base interface for TTS models
"""

import argparse
from typing import Dict

from .logger import logger


class TTSModel:
    """Base TTS Model Interface"""
    
    def __init__(self, config: Dict, args: argparse.Namespace):
        self.config = config
        self.args = args
        self.model = None
        self._initialize_model()
        logger.success("TTS model initialized")
    
    def _initialize_model(self):
        """Initialize the TTS model (to be implemented by subclasses)"""
        raise NotImplementedError
    
    def synthesize(self, text: str, output_path: str) -> bool:
        """Synthesize speech from text (to be implemented by subclasses)"""
        raise NotImplementedError