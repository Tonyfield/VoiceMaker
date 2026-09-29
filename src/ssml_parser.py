#!/usr/bin/env python3
"""
SSML Parser Module
Handles SSML parsing, validation, and text extraction
"""

import xml.etree.ElementTree as ET
from typing import Tuple, Optional


class SSMLParser:
    """SSML Parser and Validator"""
    
    @staticmethod
    def is_ssml(text: str) -> bool:
        """Check if text is in SSML format"""
        text = text.strip()
        return text.startswith('<speak') and text.endswith('</speak>')
    
    @staticmethod
    def validate_ssml(ssml_text: str, max_tokens: int) -> Tuple[bool, Optional[str]]:
        """Validate SSML text and check token limit"""
        try:
            root = ET.fromstring(ssml_text)
            
            # Check if root is <speak> (handle namespace)
            root_tag = root.tag.split('}')[-1] if '}' in root.tag else root.tag
            if root_tag != 'speak':
                return False, f"Root element must be <speak>, got <{root_tag}>"
            
            # Estimate token count (rough estimation)
            text_content = ' '.join(root.itertext())
            estimated_tokens = len(text_content.split()) * 1.5  # Rough estimation
            
            if estimated_tokens > max_tokens:
                return False, f"SSML content exceeds maximum token limit: {estimated_tokens} > {max_tokens}"
            
            return True, None
            
        except ET.ParseError as e:
            return False, f"Invalid SSML format: {str(e)}"
    
    @staticmethod
    def extract_text_from_ssml(ssml_text: str) -> str:
        """Extract plain text from SSML"""
        try:
            root = ET.fromstring(ssml_text)
            return ' '.join(root.itertext())
        except ET.ParseError:
            return ssml_text