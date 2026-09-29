"""
Text utility functions for TTS Voice Cloning.
"""
import re
from typing import List, Optional, Tuple


def clean_text(text: str) -> str:
    """
    Clean text for TTS synthesis.
    
    Args:
        text: Input text
        
    Returns:
        Cleaned text
    """
    # Remove extra whitespace
    text = re.sub(r"\s+", " ", text)
    
    # Remove control characters
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", text)
    
    # Strip leading/trailing whitespace
    text = text.strip()
    
    return text


def split_text(
    text: str,
    max_length: int = 500,
    split_on_sentence: bool = True
) -> List[str]:
    """
    Split text into chunks for TTS synthesis.
    
    Args:
        text: Input text
        max_length: Maximum length of each chunk
        split_on_sentence: Whether to split on sentence boundaries
        
    Returns:
        List of text chunks
    """
    text = clean_text(text)
    
    if len(text) <= max_length:
        return [text]
    
    chunks = []
    
    if split_on_sentence:
        # Split on sentence boundaries
        sentences = re.split(r"([。！？.!?])", text)
        sentences = [s1 + s2 for s1, s2 in zip(sentences[::2], sentences[1::2] + [""])]
        
        current_chunk = ""
        for sentence in sentences:
            if len(current_chunk) + len(sentence) <= max_length:
                current_chunk += sentence
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence
        
        if current_chunk:
            chunks.append(current_chunk.strip())
    else:
        # Simple character-based split
        for i in range(0, len(text), max_length):
            chunks.append(text[i:i + max_length])
    
    return [c for c in chunks if c.strip()]


def detect_language(text: str) -> str:
    """
    Detect the language of text.
    
    Args:
        text: Input text
        
    Returns:
        Language code (zh-cn, en, ja, ko, etc.)
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
        
        return lang_map.get(detected, "en")
        
    except Exception:
        # Fallback: check for Chinese characters
        chinese_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
        total_alpha = sum(1 for c in text if c.isalpha())
        
        if total_alpha > 0 and chinese_chars / total_alpha > 0.3:
            return "zh-cn"
        
        return "en"


def estimate_speech_duration(
    text: str,
    words_per_minute: int = 150,
    chars_per_second_chinese: float = 4.0
) -> float:
    """
    Estimate the duration of synthesized speech.
    
    Args:
        text: Input text
        words_per_minute: Speaking rate for English
        chars_per_second_chinese: Characters per second for Chinese
        
    Returns:
        Estimated duration in seconds
    """
    language = detect_language(text)
    
    if language == "zh-cn":
        # Chinese: count characters
        chinese_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
        return chinese_chars / chars_per_second_chinese
    else:
        # English and other languages: count words
        words = len(text.split())
        return (words / words_per_minute) * 60


def format_text_for_tts(
    text: str,
    remove_emojis: bool = True,
    expand_abbreviations: bool = True
) -> str:
    """
    Format text for TTS synthesis.
    
    Args:
        text: Input text
        remove_emojis: Whether to remove emoji characters
        expand_abbreviations: Whether to expand common abbreviations
        
    Returns:
        Formatted text
    """
    text = clean_text(text)
    
    if remove_emojis:
        # Remove emojis
        text = re.sub(r"[\U00010000-\U0010ffff]", "", text)
    
    if expand_abbreviations:
        # Common abbreviations
        abbreviations = {
            r"\bMr\.": "Mister",
            r"\bMrs\.": "Misses",
            r"\bDr\.": "Doctor",
            r"\bProf\.": "Professor",
            r"\bvs\.": "versus",
            r"\be\.g\.": "for example",
            r"\bi\.e\.": "that is",
            r"\betc\.": "etcetera",
        }
        
        for pattern, replacement in abbreviations.items():
            text = re.sub(pattern, replacement, text)
    
    return text.strip()


def validate_text(text: str, max_length: int = 5000) -> Tuple[bool, str]:
    """
    Validate text for TTS synthesis.
    
    Args:
        text: Input text
        max_length: Maximum allowed text length
        
    Returns:
        Tuple of (is_valid, message)
    """
    if not text or not text.strip():
        return False, "Text is empty"
    
    cleaned = clean_text(text)
    
    if len(cleaned) > max_length:
        return False, f"Text too long: {len(cleaned)} characters (maximum: {max_length})"
    
    # Check for valid characters
    if not any(c.isalpha() or c.isdigit() for c in cleaned):
        return False, "Text contains no alphanumeric characters"
    
    return True, f"Valid text: {len(cleaned)} characters"