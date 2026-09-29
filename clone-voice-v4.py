#!/usr/bin/env python3
"""
TTS Voice Cloning Script v4
Based on v3, replaces local TTS model with IndexTTS-2.5 HTTP API
(http://10.0.13.209:20213/api/synthesize).
Keeps epitran pinyin preprocessing for Chinese text.
"""

import argparse
import glob
import json
import os
import re
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import httpx
import yaml
from loguru import logger

# Import modules from src directory
from src.tts_profile import TTSProfile
from src.ssml_parser import SSMLParser
from src.text_segmenter import TextSegmenter

# Epitran lazy import (only loaded when --phonetic is enabled)
_EPITRAN_PATH = os.path.join(os.path.dirname(__file__), "..", "epitran")


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def setup_logging(verbose: bool = False):
    logger.remove()

    log_dir = Path("log")
    log_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / f"clone-voice-v4_{timestamp}.log"

    logger.level("TRACE", color="<dim><cyan>")
    logger.level("SUCCESS", color="<bold><green>")

    file_format = (
        "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
        "{level: <8} | "
        "{name}:{function}:{line: <4} | "
        "{message}"
    )

    logger.add(
        log_path,
        level="DEBUG",
        format=file_format,
        encoding="utf-8",
        rotation="10 MB",
        retention="7 days",
        enqueue=True,
    )

    console_level = "DEBUG" if verbose else "INFO"
    logger.add(
        sys.stderr,
        level=console_level,
        format="<level>{level: <8}</level> | <level>{message}</level>",
        colorize=True,
        enqueue=True,
    )

    logger.debug("Verbose mode enabled")
    logger.info(f"Log file: {log_path}")

    return logger


# ---------------------------------------------------------------------------
# Graceful shutdown handling
# ---------------------------------------------------------------------------

_shutdown_requested = False


def _signal_handler(signum, frame):
    global _shutdown_requested
    sig_name = signal.Signals(signum).name
    if _shutdown_requested:
        logger.warning(f"Received {sig_name} again, forcing exit")
        sys.exit(1)
    _shutdown_requested = True
    logger.warning(f"Received {sig_name}, finishing current sentence then exiting gracefully...")
    logger.warning("Press Ctrl+C again to force quit")


def _install_signal_handlers():
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)


# ---------------------------------------------------------------------------
# Epitran / CC-CEDICT helpers (from scripts/phonetic2.py)
# ---------------------------------------------------------------------------

_PINYIN_LANGS = {"cmn-Hans", "cmn-Hant"}
_CEDICT_LANGS = {"cmn-Hans", "cmn-Hant", "yue-Hant"}


def _cedict_cache_path() -> str:
    from epitran import download
    return os.path.join(download.base_dir(), "cedict.txt")


def _find_local_cedict() -> Optional[str]:
    candidates = [
        os.path.join(os.path.dirname(__file__), "..", "cedict_1_0_ts_utf-8_mdbg.txt"),
        os.path.join(os.path.dirname(__file__), "..", "cedict.txt"),
    ]
    for c in candidates:
        c = os.path.normpath(c)
        if os.path.exists(c):
            return c
    return None


def _ensure_cedict(max_retries: int = 3, delay: int = 5) -> Optional[str]:
    local = _find_local_cedict()
    if local:
        sz = os.path.getsize(local)
        logger.info(f"Using local dict: {local} ({sz:,} bytes)")
        return local

    from epitran import download
    cedict_url = download.CEDICT_URL
    logger.info(f"CC-CEDICT not cached, downloading:& {cedict_url}")

    import requests
    import gzip

    cache_path = _cedict_cache_path()
    gz_path = os.path.join(download.base_dir(), "cedict.txt.gz")

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"Download attempt {attempt}/{max_retries}...")
            r = requests.get(cedict_url, timeout=120)
            r.raise_for_status()

            os.makedirs(download.base_dir(), exist_ok=True)
            with open(gz_path, "wb") as f:
                f.write(r.content)

            with gzip.open(gz_path, "rb") as ip_byte, open(cache_path, "w", encoding="utf-8") as op:
                op.write(ip_byte.read().decode("utf-8"))

            if os.path.exists(gz_path):
                os.remove(gz_path)

            sz = os.path.getsize(cache_path)
            logger.success(f"CC-CEDICT downloaded: {cache_path} ({sz:,} bytes)")
            return cache_path
        except Exception as e:
            logger.warning(f"Download failed (attempt {attempt}/{max_retries}): {e}")
            if os.path.exists(gz_path):
                os.remove(gz_path)
            if attempt < max_retries:
                logger.info(f"Retrying in {delay}s...")
                time.sleep(delay)
            else:
                logger.error(f"CC-CEDICT download failed.")
                logger.info(f"Manual download: {cedict_url}")
                logger.info(f"Save to: {cache_path}")
                return None


def _convert_text_to_pinyin(text: str, epi, fmt: str = "cedict") -> Tuple[str, List[Dict]]:
    cedict_obj = epi.epi.cedict
    tokens = cedict_obj.tokenize(text)

    if fmt in ("ipa", "ipa-tones"):
        ipa_result = epi.epi.transliterate(text)
        return ipa_result, [{"token": text, "phonetic": ipa_result, "source": "epitran-ipa", "cedict_match": None}]

    pinyin_parts = []
    token_details: List[Dict] = []
    for token in tokens:
        if token in cedict_obj.hanzi:
            pinyin, english = cedict_obj.hanzi[token]
            pinyin_str = " ".join(pinyin)
            if fmt == "cedict":
                formatted = pinyin_str
            elif fmt == "notone":
                formatted = re.sub(r'[1-5]', '', pinyin_str)
            elif fmt == "tonemark":
                formatted = _pinyin_add_tonemarks(pinyin_str)
            else:
                formatted = pinyin_str
            pinyin_parts.append(formatted)
            token_details.append({
                "token": token,
                "cedict_raw": " ".join(pinyin),
                "formatted": formatted,
                "english": " / ".join(english[:3]),
                "source": "cedict",
                "cedict_match": True,
            })
        else:
            pinyin_parts.append(token)
            token_details.append({
                "token": token,
                "cedict_raw": None,
                "formatted": None,
                "english": None,
                "source": "passthrough",
                "cedict_match": False,
            })
    return " ".join(pinyin_parts), token_details


def _build_tts_input(token_details: List[Dict]) -> str:
    """Build TTS input: CEDICT-matched tokens use pinyin, others keep original Chinese.
    If a matched pinyin is only 1 character (e.g. 'A', 'D' — not a real syllable),
    keep the original Chinese character instead.
    """
    parts = []
    for d in token_details:
        if d.get("cedict_match") and d.get("formatted") is not None:
            formatted = d["formatted"]
            if len(formatted) <= 1:
                parts.append(d["token"])
            else:
                parts.append(formatted)
        else:
            parts.append(d["token"])
    return " ".join(parts)


_PINYIN_TONE_MAP = {
    'a': 'āáǎàa', 'e': 'ēéěèe', 'i': 'īíǐìi',
    'o': 'ōóǒòo', 'u': 'ūúǔùu', 'ü': 'ǖǘǚǜü',
}


def _pinyin_add_tonemarks(syllable: str) -> str:
    m = re.match(r'^([a-z]+?)([1-5])$', syllable)
    if not m:
        return syllable
    base, tone = m.group(1), int(m.group(2))
    if tone == 5 or tone == 0:
        return base
    idx = tone - 1
    target = -1
    for i, ch in enumerate(base):
        if ch in _PINYIN_TONE_MAP:
            if ch in ('a', 'o', 'e'):
                target = i
                break
            target = i
    if target == -1:
        return base
    ch = base[target]
    replacement = _PINYIN_TONE_MAP[ch][idx]
    if 'ü' in base and ch == 'u':
        replacement = _PINYIN_TONE_MAP['ü'][idx]
    return base[:target] + replacement + base[target + 1:]


# ---------------------------------------------------------------------------
# Phonetic preprocessor
# ---------------------------------------------------------------------------

class PhoneticPreprocessor:
    """Wraps epitran for Chinese→pinyin conversion."""

    VALID_FORMATS = ("cedict", "notone", "tonemark", "ipa", "ipa-tones")

    def __init__(self, cedict_file: Optional[str] = None, max_retries: int = 3, fmt: str = "cedict"):
        self._epi = None
        self._cedict_file = cedict_file
        self._max_retries = max_retries
        self._fmt = fmt if fmt in self.VALID_FORMATS else "cedict"

    def initialize(self):
        epi_kwargs = {}
        if self._cedict_file:
            if not os.path.exists(self._cedict_file):
                raise FileNotFoundError(f"CC-CEDICT file not found: {self._cedict_file}")
            logger.info(f"Using specified dict: {self._cedict_file}")
            epi_kwargs["cedict_file"] = self._cedict_file
        else:
            cedict_path = _ensure_cedict(max_retries=self._max_retries)
            if cedict_path:
                epi_kwargs["cedict_file"] = cedict_path
            else:
                raise RuntimeError("Cannot obtain CC-CEDICT dictionary. Use --cedict to specify manually.")

        if self._fmt == "ipa-tones":
            epi_kwargs["tones"] = True

        sys.path.insert(0, _EPITRAN_PATH)
        import epitran
        logger.info(f"Initializing epitran (cmn-Hans, fmt={self._fmt})...")
        self._epi = epitran.Epitran("cmn-Hans", ligatures=False, **epi_kwargs)
        logger.success("Epitran initialized.")

    def convert(self, text: str) -> Tuple[str, List[Dict]]:
        if self._epi is None:
            raise RuntimeError("PhoneticPreprocessor not initialized. Call initialize() first.")
        return _convert_text_to_pinyin(text, self._epi, fmt=self._fmt)

    @property
    def is_initialized(self) -> bool:
        return self._epi is not None

    @property
    def fmt(self) -> str:
        return self._fmt


# ---------------------------------------------------------------------------
# IndexTTS-2.5 HTTP API client
# ---------------------------------------------------------------------------

class IndexTTS25API:
    """HTTP client for IndexTTS-2.5 API (http://10.0.13.209:20213)."""

    def __init__(self, base_url: str, reference_audio: str, language: str = "auto", timeout: int = 600):
        self.base_url = base_url.rstrip("/")
        self.reference_audio = reference_audio
        self.language = language
        self.timeout = timeout

        if not os.path.exists(reference_audio):
            raise FileNotFoundError(f"Reference audio not found: {reference_audio}")

        # Health check
        self._check_health()

    def _check_health(self):
        health_url = f"{self.base_url}/api/health"
        logger.info(f"Checking API health: {health_url}")
        try:
            r = httpx.get(health_url, timeout=10)
            r.raise_for_status()
            logger.success(f"API health OK: {r.text}")
        except Exception as e:
            logger.warning(f"Health check failed: {e}")

    def synthesize(self, text: str, output_path: str) -> bool:
        """Synthesize speech via HTTP API and save to output_path."""
        start_time = time.time()

        try:
            output_path = Path(output_path)
            output_path = output_path.resolve()
            output_path.parent.mkdir(parents=True, exist_ok=True)

            text_length = len(text)
            estimated_tokens = int(text_length / 4)

            logger.info(f"--- TTS API Request ---")
            logger.info(f"  [文本]      {text}")
            logger.info(f"  [文本长度]  {text_length} chars (~{estimated_tokens} tokens)")
            logger.info(f"  [语言]      {self.language}")
            logger.info(f"  [参考音频]  {self.reference_audio}")

            # Build multipart form data
            with open(self.reference_audio, "rb") as ref_file:
                files = {
                    "reference_audio": ("reference.wav", ref_file, "audio/wav"),
                }
                data = {
                    "text": text,
                    "language": self.language,
                }

                synthesize_url = f"{self.base_url}/api/synthesize"
                logger.info(f"  [POST] {synthesize_url}")

                response = httpx.post(
                    synthesize_url,
                    data=data,
                    files=files,
                    timeout=self.timeout,
                )

            if response.status_code != 200:
                logger.error(f"API returned HTTP {response.status_code}")
                try:
                    detail = response.json()
                    logger.error(f"  Detail: {detail}")
                except Exception:
                    logger.error(f"  Body: {response.text[:500]}")
                return False

            # Save WAV bytes to file
            output_path.write_bytes(response.content)
            file_size = output_path.stat().st_size

            elapsed_time = time.time() - start_time

            logger.success("Audio synthesis completed!")
            logger.info(f"  [输出]  {output_path}")
            logger.info(f"  [大小]  {file_size:,} bytes")
            logger.info(f"  [耗时]  {elapsed_time:.2f}s")
            logger.info(f"  [速率]  {text_length / elapsed_time:.1f} chars/sec")

            return True

        except Exception as e:
            elapsed_time = time.time() - start_time
            logger.error(f"Synthesis failed: {e}")
            logger.error(f"Time elapsed: {elapsed_time:.2f}s")
            import traceback
            traceback.print_exc()
            return False


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def split_sentences(text: str) -> List[str]:
    """Split text into sentences by Chinese/English sentence-ending punctuation."""
    pattern = r'[^。！？\.\!\?\n]+[。！？\.\!\?]?[\'\"）\]》」』]?'
    raw = re.findall(pattern, text)

    sentences = []
    for s in raw:
        s = s.strip()
        if s:
            sentences.append(s)

    if not sentences and text.strip():
        sentences = [text.strip()]

    return sentences


def expand_text_files(pattern: str) -> List[Path]:
    if not pattern.lower().endswith('.txt'):
        raise ValueError("File pattern must end with .txt")

    if '*' in pattern or '?' in pattern:
        matched_files = glob.glob(pattern, recursive=False)
        text_files = []
        for file_path in matched_files:
            path = Path(file_path)
            if path.exists() and path.suffix.lower() == '.txt':
                text_files.append(path)
        text_files.sort()
        return text_files
    else:
        path = Path(pattern)
        if path.exists() and path.suffix.lower() == '.txt':
            return [path]
        else:
            return []


def main():
    """Main function"""

    # Check for help flag early, before loading profile
    if '-h' in sys.argv or '--help' in sys.argv:
        print("TTS Voice Cloning Script v4 (IndexTTS-2.5 API)")
        print()
        print("Usage: python clone-voice-v4.py -t TEXT_FILE -o OUTPUT [options]")
        print()
        print("Required arguments:")
        print("  -t, --text-file FILE   Input text file path(s), supports wildcards (e.g., *.txt)")
        print("  -o, --output FILE      Output audio file path")
        print("  -r, --reference-audio  Path to reference audio file for voice cloning")
        print()
        print("API arguments:")
        print("  --api-base-url URL     IndexTTS-2.5 API base URL (default: http://10.0.13.209:20213)")
        print("  --language LANG        Language code (default: auto)")
        print("  --api-timeout SEC      API request timeout in seconds (default: 600)")
        print()
        print("Optional arguments:")
        print("  -p, --profile FILE     Path to TTS profile YAML file (default: tts-profiles.yaml)")
        print()
        print("v4 - Phonetic preprocessing options:")
        print("  --phonetic             Enable epitran pinyin preprocessing (Chinese → pinyin)")
        print("  --phonetic-format FMT  Output format: cedict|notone|tonemark|ipa|ipa-tones (default: cedict)")
        print("  --cedict FILE          Path to CC-CEDICT dictionary file")
        print("  --phonetic-retries N   CC-CEDICT download retries (default: 3)")
        print()
        print("Sentence range options (plain text only):")
        print("  -s, --start N          Start sentence (1-based, default: 1). Negative counts from end.")
        print("  -e, --end N            End sentence (1-based inclusive, default: -1 = last). Negative counts from end.")
        print()
        print("Logging options:")
        print("  -v, --verbose          Enable verbose/debug logging output")
        sys.exit(0)

    # ---- Parse arguments ----
    parser = argparse.ArgumentParser(
        description="TTS Voice Cloning Script v4 - IndexTTS-2.5 API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Required arguments
    parser.add_argument('-t', '--text-file', required=True, type=str,
                        help='Input text file path(s). Supports wildcards (e.g., text/*.txt, input_*.txt). Must end with .txt')
    parser.add_argument('-o', '--output', required=True, type=str,
                        help='Output audio file path')
    parser.add_argument('-r', '--reference-audio', required=True, type=str,
                        help='Path to reference audio file for voice cloning')

    # API arguments
    parser.add_argument('--api-base-url', type=str, default='http://10.0.13.209:20213',
                        help='IndexTTS-2.5 API base URL (default: http://10.0.13.209:20213)')
    parser.add_argument('--language', type=str, default='auto',
                        help='Language code for TTS synthesis (default: auto)')
    parser.add_argument('--api-timeout', type=int, default=600,
                        help='API request timeout in seconds (default: 600)')

    # Profile
    parser.add_argument('-p', '--profile', default='tts-profiles.yaml', type=str,
                        help='Path to TTS profile YAML file (default: tts-profiles.yaml)')

    # Phonetic preprocessing options
    parser.add_argument('--phonetic', action='store_true', default=False,
                        help='Enable epitran pinyin preprocessing (Chinese text → pinyin)')
    parser.add_argument('--phonetic-format', type=str, default='cedict',
                        choices=['cedict', 'notone', 'tonemark', 'ipa', 'ipa-tones'],
                        help='Phonetic output format (default: cedict)')
    parser.add_argument('--cedict', type=str, default=None,
                        help='Path to CC-CEDICT dictionary file (optional, auto-download if not provided)')
    parser.add_argument('--phonetic-retries', type=int, default=3,
                        help='CC-CEDICT download retries (default: 3)')

    # Sentence range options
    parser.add_argument('-s', '--start', type=int, default=1,
                        help='Start sentence (1-based). Default: 1 (first sentence). Negative: -1 = last.')
    parser.add_argument('-e', '--end', type=int, default=-1,
                        help='End sentence (1-based, inclusive). Default: -1 (last sentence). Negative: -1 = last.')

    # Logging options
    parser.add_argument('-v', '--verbose', action='store_true', default=False,
                        help='Enable verbose/debug logging output')

    args = parser.parse_args()

    # ---- Setup logging ----
    setup_logging(verbose=args.verbose)

    # Install signal handlers for graceful shutdown
    _install_signal_handlers()

    # ---- Reference audio validation ----
    if not os.path.exists(args.reference_audio):
        logger.error(f"Reference audio file not found: {args.reference_audio}")
        return 1

    logger.info(f"Reference audio: {args.reference_audio}")

    # ---- v4: Initialize IndexTTS-2.5 API client ----
    logger.info(f"--- IndexTTS-2.5 API ---")
    logger.info(f"Base URL: {args.api_base_url}")
    logger.info(f"Language: {args.language}")
    tts_api = IndexTTS25API(
        base_url=args.api_base_url,
        reference_audio=args.reference_audio,
        language=args.language,
        timeout=args.api_timeout,
    )
    logger.success(f"IndexTTS-2.5 API client ready")

    # ---- v4: Phonetic preprocessor (optional) ----
    phonetic = None
    if args.phonetic:
        fmt = args.phonetic_format
        logger.info("--- Phonetic Preprocessing ---")
        logger.info(f"Mode: Chinese text → {fmt} format (epitran + CC-CEDICT)")
        phonetic = PhoneticPreprocessor(
            cedict_file=args.cedict,
            max_retries=args.phonetic_retries,
            fmt=fmt,
        )
        phonetic.initialize()
        logger.success(f"Phonetic preprocessor ready (format: {fmt})")

    # Expand wildcard patterns and find text files
    text_files = expand_text_files(args.text_file)

    if not text_files:
        logger.error(f"No .txt files found matching pattern: {args.text_file}")
        return 1

    logger.info(f"Found {len(text_files)} text file(s) to process")
    for i, file_path in enumerate(text_files, 1):
        logger.info(f"  {i}. {file_path}")

    # Process each text file
    total_success = 0
    total_segments = 0
    interrupted = False

    try:
        for file_idx, text_file in enumerate(text_files, 1):
            if _shutdown_requested:
                logger.warning("Shutdown requested, stopping file processing")
                interrupted = True
                break

            logger.info(f"{'=' * 60}")
            logger.info(f"Processing file {file_idx}/{len(text_files)}: {text_file.name}")
            logger.info(f"{'=' * 60}")

            # Read input text
            try:
                with open(text_file, 'r', encoding='utf-8') as f:
                    text = f.read()
            except Exception as e:
                logger.error(f"Failed to read {text_file}: {e}")
                continue

            logger.info(f"Text length: {len(text)} characters")
            logger.debug(f"Text preview: {text[:120]}...")

            # Determine output directory + audio suffix
            output_path = Path(args.output)
            audio_suffix = output_path.suffix if output_path.suffix else ".wav"
            if output_path.suffix:
                output_dir = output_path.parent
            else:
                output_dir = output_path
            output_dir.mkdir(parents=True, exist_ok=True)

            # Check if text is SSML
            ssml_parser = SSMLParser()
            is_ssml = ssml_parser.is_ssml(text)

            if is_ssml:
                logger.info("Detected SSML format")

                plain_text = ssml_parser.extract_text_from_ssml(text)
                logger.info(f"Extracted plain text length: {len(plain_text)} characters")

                # Use a generous max_tokens for API-based TTS (API handles its own limits)
                max_tokens = 4096
                is_valid, error_msg = ssml_parser.validate_ssml(text, max_tokens)
                if not is_valid:
                    logger.warning(f"{error_msg} - SSML text is too long, will segment and process in parts")

                segmenter = TextSegmenter()
                segments = segmenter.segment_text(plain_text, max_tokens, use_cpu_mode=False)
                logger.info(f"Text segmented into {len(segments)} parts")

                file_success = 0
                for i, text_segment in enumerate(segments):
                    if _shutdown_requested:
                        logger.warning("Shutdown requested, stopping SSML segment processing")
                        interrupted = True
                        break
                    segment_output = output_dir / f"{text_file.stem}-{i+1:04d}{audio_suffix}"
                    logger.info(f"Synthesizing segment {i+1}/{len(segments)} (len={len(text_segment)}) -> {segment_output}")
                    logger.debug(f"Segment preview: {text_segment[:80]}...")
                    if tts_api.synthesize(text_segment, str(segment_output)):
                        file_success += 1
                        logger.success(f"Segment {i+1} succeeded: {segment_output}")
                    else:
                        logger.error(f"Failed to synthesize segment {i+1}: {segment_output}")

                logger.info(f"File {text_file.name}: {file_success}/{len(segments)} segments successful")
                total_success += file_success
                total_segments += len(segments)
                if interrupted:
                    break
                continue

            # ---- Plain text: split into sentences ----
            all_sentences = split_sentences(text)
            n_sentences = len(all_sentences)
            logger.info(f"Sentence-based segmentation: {n_sentences} sentences total")

            # Resolve --start / --end indices
            start = args.start
            end = args.end

            if start > 0:
                start_idx = start - 1
            else:
                start_idx = n_sentences + start

            if end > 0:
                end_idx = end
            else:
                end_idx = n_sentences + end + 1

            start_idx = max(0, min(start_idx, n_sentences))
            end_idx = max(0, min(end_idx, n_sentences))

            if start_idx >= end_idx:
                logger.error(f"Invalid sentence range: start={start}, end={end} resolved to [{start_idx}:{end_idx}] (total {n_sentences} sentences). Skipping file.")
                continue

            sentences = all_sentences[start_idx:end_idx]
            logger.info(f"Selected sentences {start}..{end} → indices [{start_idx}:{end_idx}] → {len(sentences)} sentence(s) to synthesize")

            # Pre-compute phonetic for each sentence (if enabled)
            sentence_phonetics: List[Optional[str]] = [None] * len(sentences)
            sentence_details: List[Optional[List[Dict]]] = [None] * len(sentences)
            if phonetic and phonetic.is_initialized:
                logger.info("Computing phonetic (pinyin) for each selected sentence...")
                for i, sent in enumerate(sentences):
                    try:
                        phonetic_str, details = phonetic.convert(sent)
                        sentence_phonetics[i] = phonetic_str
                        sentence_details[i] = details
                    except Exception as e:
                        logger.warning(f"Phonetic conversion failed for sentence {start_idx + i + 1}: {e}")
                        sentence_phonetics[i] = None
                        sentence_details[i] = None

            # Synthesize each sentence
            file_success = 0
            for i, sentence in enumerate(sentences):
                if _shutdown_requested:
                    logger.warning("Shutdown requested, stopping sentence processing")
                    interrupted = True
                    break

                global_idx = start_idx + i + 1
                phonetic_str = sentence_phonetics[i]
                details = sentence_details[i]

                # Build TTS input
                if details is not None:
                    tts_input = _build_tts_input(details)
                elif phonetic_str is not None:
                    tts_input = phonetic_str
                else:
                    tts_input = sentence

                segment_output = output_dir / f"{text_file.stem}-{global_idx:04d}{audio_suffix}"

                phonetic_label = {
                    "cedict": "拼音(num)", "notone": "拼音(notone)",
                    "tonemark": "拼音(tone)", "ipa": "IPA",
                    "ipa-tones": "IPA(tones)",
                }.get(phonetic.fmt, "拼音") if phonetic else ""

                logger.info(f"—— Sentence {global_idx}/{n_sentences} (len={len(sentence)}) ——")
                logger.info(f"  [原文]        {sentence}")
                if phonetic_str is not None:
                    logger.info(f"  [{phonetic_label}]    {phonetic_str}")
                else:
                    logger.info(f"  [{phonetic_label}]    (disabled / failed)")
                logger.info(f"  [→ TTS]       {tts_input}")
                logger.info(f"  [输出]        {segment_output}")

                if details:
                    for d in details:
                        if d.get("cedict_match"):
                            formatted = d.get("formatted", "")
                            if len(formatted) <= 1:
                                logger.info(f"  [CEDICT]  {d['token']} → {formatted}  ({d['english']})  ⚠ 单字符拼音，保留原字")
                            else:
                                logger.info(f"  [CEDICT]  {d['token']} → {formatted}  ({d['english']})")
                        elif d.get("source") == "passthrough":
                            logger.info(f"  [原字符]  '{d['token']}' (CEDICT 未收录，保留原字符)")

                if tts_api.synthesize(tts_input, str(segment_output)):
                    file_success += 1
                    logger.success(f"Sentence {global_idx} succeeded")
                else:
                    logger.error(f"Sentence {global_idx} failed")

            logger.info(f"File {text_file.name}: {file_success}/{len(sentences)} sentences successful")
            total_success += file_success
            total_segments += len(sentences)

            if interrupted:
                break

    except KeyboardInterrupt:
        logger.warning("KeyboardInterrupt received, shutting down gracefully")
        interrupted = True

    # Final summary
    logger.info(f"{'=' * 60}")
    if interrupted:
        logger.info("Summary (interrupted)")
    else:
        logger.info("Overall Summary")
    logger.info(f"{'=' * 60}")
    logger.info(f"Total files processed: {len(text_files)}")
    logger.info(f"Total segments: {total_segments}")
    logger.info(f"Successful segments: {total_success}")
    logger.info(f"Failed segments: {total_segments - total_success}")

    if interrupted:
        logger.warning("Process was interrupted by user signal")
        return 130

    if total_success == total_segments:
        logger.success("All segments synthesized successfully!")
        return 0
    else:
        logger.error(f"{total_segments - total_success} segment(s) failed to synthesize")
        return 1


if __name__ == '__main__':
    sys.exit(main())