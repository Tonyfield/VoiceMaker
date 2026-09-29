#!/usr/bin/env python3
"""
Text Segmenter Module
Handles text segmentation for TTS processing
"""

import re
from typing import List

from .logger import logger


class TextSegmenter:
    """Text Segmentation for TTS"""
    
    @staticmethod
    def segment_text(text: str, max_tokens: int, use_cpu_mode: bool = False) -> List[str]:
        """
        Segment text into chunks while keeping sentences complete
        Uses 60% of max_tokens as the segment limit
        For CPU mode, uses 15% to reduce memory usage
        """
        # Use smaller segments for CPU mode to reduce memory usage
        segment_limit = int(max_tokens * 0.15) if use_cpu_mode else int(max_tokens * 0.6)
        
        logger.debug(f"Segment limit: {segment_limit} tokens (CPU mode: {use_cpu_mode})")
        
        # Split into sentences
        sentences = re.split(r'([。！？；\n])', text)
        
        # Reconstruct sentences with punctuation
        reconstructed = []
        for i in range(0, len(sentences) - 1, 2):
            if i + 1 < len(sentences):
                sentence = sentences[i] + sentences[i + 1]
                if sentence.strip():
                    reconstructed.append(sentence)
        
        # Group sentences into segments
        segments = []
        current_segment = ""
        current_tokens = 0
        
        for sentence in reconstructed:
            sentence_tokens = len(sentence.split())
            
            if current_tokens + sentence_tokens <= segment_limit:
                current_segment += sentence
                current_tokens += sentence_tokens
            else:
                if current_segment:
                    segments.append(current_segment)
                current_segment = sentence
                current_tokens = sentence_tokens
        
        if current_segment:
            segments.append(current_segment)
        
        return segments