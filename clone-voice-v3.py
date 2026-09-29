#!/usr/bin/env python3
"""
TTS Voice Cloning Script v3
Based on v1, adds epitran pinyin preprocessing for Qwen TTS.
Converts Chinese text to numbered-tone pinyin (e.g., "ni3 hao3") before synthesis.
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
import xml.etree.ElementTree as ET

import yaml
from loguru import logger

# Import modules from src directory
from src.tts_profile import TTSProfile
from src.ssml_parser import SSMLParser
from src.text_segmenter import TextSegmenter
from src.tts_factory import TTSFactory

# Epitran imports (add epitran to path)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "epitran"))
import epitran
from epitran import download


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def setup_logging(verbose: bool = False):
    logger.remove()

    log_dir = Path("log")
    log_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / f"clone-voice-v3_{timestamp}.log"

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
    # cache_path = _cedict_cache_path()

    # if os.path.exists(cache_path):
    #     sz = os.path.getsize(cache_path)
    #     logger.info(f"CC-CEDICT cached: {cache_path} ({sz:,} bytes)")
    #     return cache_path

    local = _find_local_cedict()
    if local:
        sz = os.path.getsize(local)
        logger.info(f"Using local dict: {local} ({sz:,} bytes)")
        # try:
        #     os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        #     import shutil
        #     shutil.copy2(local, cache_path)
        #     logger.info(f"Copied to cache: {cache_path}")
        # except Exception as e:
        #     logger.warning(f"Copy to cache failed: {e}, using local file directly")
        # return cache_path if os.path.exists(cache_path) else local
        return local

    cedict_url = download.CEDICT_URL
    logger.info(f"CC-CEDICT not cached, downloading: {cedict_url}")

    import requests
    import gzip

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


def _convert_text_to_pinyin(text: str, epi: epitran.Epitran, fmt: str = "cedict") -> Tuple[str, List[Dict]]:
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
        self._epi: Optional[epitran.Epitran] = None
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
# Core functions (from v1, adapted)
# ---------------------------------------------------------------------------

def split_sentences(text: str) -> List[str]:
    """Split text into sentences by Chinese/English sentence-ending punctuation.

    Preserves the punctuation mark with each sentence. Strips leading/trailing
    whitespace from each sentence and drops empty ones.
    """
    # Match any run of characters up to a sentence terminator (。！？.!?)
    # possibly followed by closing quotes or brackets, plus optional whitespace.
    pattern = r'[^。！？\.\!\?\n]+[。！？\.\!\?]?[\'\"）\]》」』]?'
    raw = re.findall(pattern, text)

    sentences = []
    for s in raw:
        s = s.strip()
        if s:
            sentences.append(s)

    # Fallback: if no sentence markers were found, treat entire text as one sentence.
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


def parse_arguments(profile: TTSProfile) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="TTS Voice Cloning Script v3 - with epitran pinyin preprocessing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage (sentence-by-sentence)
  python clone-voice-v3.py -m qwen3-tts-12hz-0.6b-base -t input.txt -o output.wav

  # With epitran pinyin preprocessing
  python clone-voice-v3.py -m qwen3-tts-12hz-0.6b-base -t input.txt -o output.wav --phonetic

  # With custom CC-CEDICT dictionary
  python clone-voice-v3.py -m qwen3-tts-12hz-0.6b-base -t input.txt -o output.wav --phonetic --cedict cedict.txt

  # Synthesize only sentences 3 to 7
  python clone-voice-v3.py -m qwen3-tts-12hz-0.6b-base -t input.txt -o output.wav -s 3 -e 7

  # Synthesize the last 2 sentences
  python clone-voice-v3.py -m qwen3-tts-12hz-0.6b-base -t input.txt -o output.wav -s -2 -e -1
        """
    )

    # Required arguments
    parser.add_argument(
        '-m', '--model',
        required=True,
        choices=profile.list_models(),
        help='TTS model to use'
    )

    parser.add_argument(
        '-t', '--text-file',
        required=True,
        type=str,
        help='Input text file path(s). Supports wildcards (e.g., text/*.txt, input_*.txt). Must end with .txt'
    )

    parser.add_argument(
        '-o', '--output',
        required=True,
        type=str,
        help='Output audio file path'
    )

    parser.add_argument(
        '-p', '--profile',
        default='tts-profiles.yaml',
        type=str,
        help='Path to TTS profile YAML file (default: tts-profiles.yaml)'
    )

    parser.add_argument(
        '--hf-mirror',
        type=str,
        default=None,
        help='Hugging Face mirror URL for faster download in China (e.g., https://hf-mirror.com)'
    )

    parser.add_argument(
        '--language',
        type=str,
        default='Chinese',
        help='Language for TTS synthesis (default: Chinese)'
    )

    # ---- v3: phonetic preprocessing options ----
    parser.add_argument(
        '--phonetic',
        action='store_true',
        default=False,
        help='Enable epitran pinyin preprocessing (Chinese text → pinyin)'
    )

    parser.add_argument(
        '--phonetic-format',
        type=str,
        default='cedict',
        choices=['cedict', 'notone', 'tonemark', 'ipa', 'ipa-tones'],
        help=(
            'Phonetic output format (default: cedict). '
            'cedict    = numbered-tone pinyin, e.g. li2 shan1  '
            'notone    = pinyin without tones, e.g. li shan  '
            'tonemark  = pinyin with Unicode tone marks, e.g. lí shān  '
            'ipa       = IPA (no tones), e.g. li ʂan  '
            'ipa-tones = IPA with Chao tone letters, e.g. li˧˥ ʂan˥'
        )
    )

    parser.add_argument(
        '--cedict',
        type=str,
        default=None,
        help='Path to CC-CEDICT dictionary file (optional, auto-download if not provided)'
    )

    parser.add_argument(
        '--phonetic-retries',
        type=int,
        default=3,
        help='CC-CEDICT download retries (default: 3)'
    )

    # ---- Sentence range options ----
    parser.add_argument(
        '-s', '--start',
        type=int,
        default=1,
        help='Start sentence (1-based). Default: 1 (first sentence). Negative: -1 = last, -2 = second-to-last.'
    )
    parser.add_argument(
        '-e', '--end',
        type=int,
        default=-1,
        help='End sentence (1-based, inclusive). Default: -1 (last sentence). Negative: -1 = last, -2 = second-to-last.'
    )

    # ---- Logging options ----
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        default=False,
        help='Enable verbose/debug logging output'
    )

    # Model-specific arguments (will be populated from profile)
    args, remaining = parser.parse_known_args()

    # Get model configuration
    model_config = profile.get_model_config(args.model)

    # Collect already-defined option strings to avoid conflicts
    existing_options = set()
    for action in parser._actions:
        existing_options.update(action.option_strings)

    # Add model-specific parameters
    if 'parameters' in model_config:
        for param_name, param_config in model_config['parameters'].items():
            arg_name = param_name.replace('_', '-')
            option_str = f'--{arg_name}'
            if option_str in existing_options:
                continue  # Skip parameters already defined as fixed arguments

            param_type = param_config.get('type', 'str')
            if param_type == 'float':
                parser.add_argument(
                    f'--{arg_name}',
                    type=float,
                    default=param_config.get('default'),
                    help=param_config.get('description', '')
                )
            elif param_type == 'int':
                parser.add_argument(
                    f'--{arg_name}',
                    type=int,
                    default=param_config.get('default'),
                    help=param_config.get('description', '')
                )
            elif param_type == 'str':
                if 'choices' in param_config:
                    parser.add_argument(
                        f'--{arg_name}',
                        type=str,
                        default=param_config.get('default'),
                        choices=param_config['choices'],
                        help=param_config.get('description', '')
                    )
                else:
                    parser.add_argument(
                        f'--{arg_name}',
                        type=str,
                        default=param_config.get('default'),
                        help=param_config.get('description', '')
                    )

    # Parse all arguments
    args = parser.parse_args()

    return args


def main():
    """Main function"""

    # Check for help flag early, before loading profile
    if '-h' in sys.argv or '--help' in sys.argv:
        prelim_parser = argparse.ArgumentParser(add_help=False)
        prelim_parser.add_argument('-p', '--profile', default='tts-profiles.yaml', type=str)
        try:
            prelim_args, _ = prelim_parser.parse_known_args()
            if os.path.exists(prelim_args.profile):
                profile = TTSProfile(prelim_args.profile)
                parse_arguments(profile)
        except Exception:
            pass
        print("TTS Voice Cloning Script v3")
        print()
        print("Usage: python clone-voice-v3.py -m MODEL -t TEXT_FILE -o OUTPUT [options]")
        print()
        print("Required arguments:")
        print("  -m, --model MODEL      TTS model to use (choices depend on profile)")
        print("  -t, --text-file FILE   Input text file path(s), supports wildcards (e.g., *.txt)")
        print("  -o, --output FILE      Output audio file path")
        print()
        print("Optional arguments:")
        print("  -p, --profile FILE     Path to TTS profile YAML file (default: tts-profiles.yaml)")
        print("  --hf-mirror URL        Hugging Face mirror URL for faster download in China")
        print("  --language LANG         Language for TTS synthesis (default: Chinese)")
        print()
        print("v3 - Phonetic preprocessing options:")
        print("  --phonetic             Enable epitran pinyin preprocessing (Chinese → pinyin)")
        print("  --phonetic-format FMT  Output format: cedict|notone|tonemark|ipa|ipa-tones (default: cedict)")
        print("  --cedict FILE          Path to CC-CEDICT dictionary file")
        print("  --phonetic-retries N   CC-CEDICT download retries (default: 3)")
        print()
        print("Sentence range options (plain text only):")
        print("  -s, --start N          Start sentence (1-based, default: 1). Negative counts from end.")
        print("  -e, --end N            End sentence (1-based inclusive, default: -1 = last). Negative counts from end.")
        print()
        print("Note: Model-specific options depend on the profile configuration.")
        print("      Place tts-profiles.yaml in the working directory for full help.")
        sys.exit(0)

    # Load profile
    profile_path = 'tts-profiles.yaml'
    if not os.path.exists(profile_path):
        print(f"Error: Profile file not found: {profile_path}")
        sys.exit(1)

    profile = TTSProfile(profile_path)

    # Parse arguments
    args = parse_arguments(profile)

    # ---- Setup logging (must happen after args are parsed) ----
    setup_logging(verbose=args.verbose)

    # Install signal handlers for graceful shutdown
    _install_signal_handlers()

    # Get model configuration
    model_config = profile.get_model_config(args.model)
    logger.info(f"Using model: {model_config['name']}")
    logger.info(f"Framework: {model_config['framework']}")
    logger.info(f"Max tokens: {model_config['max_tokens']}")
    logger.info(f"Supports SSML: {model_config['supports_ssml']}")

    # ---- v3: Initialize phonetic preprocessor if enabled ----
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

    # Check device availability
    import torch
    device = "CPU" if not torch.cuda.is_available() else "GPU"
    logger.info(f"Device: {device}")
    if device == "CPU":
        logger.warning("Running in CPU mode. Synthesis may be slower.")

    # Expand wildcard patterns and find text files
    text_files = expand_text_files(args.text_file)

    if not text_files:
        logger.error(f"No .txt files found matching pattern: {args.text_file}")
        return 1

    logger.info(f"Found {len(text_files)} text file(s) to process")
    for i, file_path in enumerate(text_files, 1):
        logger.info(f"  {i}. {file_path}")

    # Create TTS model (load once for all files)
    logger.info("Creating TTS model...")
    tts_model = TTSFactory.create_model(model_config, args)
    logger.success("TTS model created")

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

            # Determine output directory + audio suffix from the -o argument.
            # Output file per sentence: <text-file-stem>-<sentence-number>.<audio-suffix>
            output_path = Path(args.output)
            audio_suffix = output_path.suffix if output_path.suffix else ".wav"
            # Ensure output directory exists (if -o points to a file, use its parent)
            if output_path.suffix:
                output_dir = output_path.parent
            else:
                output_dir = output_path  # user gave a directory path
            output_dir.mkdir(parents=True, exist_ok=True)

            # Check if text is SSML — SSML keeps the original segmenter behaviour
            ssml_parser = SSMLParser()
            is_ssml = ssml_parser.is_ssml(text)

            if is_ssml:
                logger.info("Detected SSML format")

                plain_text = ssml_parser.extract_text_from_ssml(text)
                logger.info(f"Extracted plain text length: {len(plain_text)} characters")

                is_valid, error_msg = ssml_parser.validate_ssml(text, model_config['max_tokens'])
                if not is_valid:
                    logger.warning(f"{error_msg} - SSML text is too long, will segment and process in parts")

                segmenter = TextSegmenter()
                segments = segmenter.segment_text(plain_text, model_config['max_tokens'], use_cpu_mode=(device == "CPU"))
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
                    if tts_model.synthesize(text_segment, str(segment_output)):
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

            # ---- Plain text: split into sentences, one sentence per segment ----
            all_sentences = split_sentences(text)
            n_sentences = len(all_sentences)
            logger.info(f"Sentence-based segmentation: {n_sentences} sentences total")

            # Resolve --start / --end indices (1-based user input to 0-based Python slice)
            start = args.start
            end = args.end

            if start > 0:
                start_idx = start - 1
            else:
                start_idx = n_sentences + start  # -1 → n-1, -2 → n-2

            if end > 0:
                end_idx = end  # exclusive: sentence #end → 0-indexed #end-1 → slice[:end] stops before index end, covering 0..end-1
            else:
                end_idx = n_sentences + end + 1  # -1 → n, -2 → n-1

            # Clamp to valid range
            start_idx = max(0, min(start_idx, n_sentences))
            end_idx = max(0, min(end_idx, n_sentences))

            if start_idx >= end_idx:
                logger.error(f"Invalid sentence range: start={start}, end={end} resolved to [{start_idx}:{end_idx}] (total {n_sentences} sentences). Skipping file.")
                continue

            sentences = all_sentences[start_idx:end_idx]
            logger.info(f"Selected sentences {start}..{end} → indices [{start_idx}:{end_idx}] → {len(sentences)} sentence(s) to synthesize")

            # Pre-compute phonetic for each sentence (if enabled) so we can log both versions
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

            # Synthesize each sentence — one TTS call per sentence
            file_success = 0
            for i, sentence in enumerate(sentences):
                if _shutdown_requested:
                    logger.warning("Shutdown requested, stopping sentence processing")
                    interrupted = True
                    break

                global_idx = start_idx + i + 1  # 1-based global sentence number
                phonetic_str = sentence_phonetics[i]
                details = sentence_details[i]

                # Build TTS input: CEDICT-matched tokens → pinyin, others → original Chinese
                if details is not None:
                    tts_input = _build_tts_input(details)
                elif phonetic_str is not None:
                    tts_input = phonetic_str
                else:
                    tts_input = sentence

                # Output path is always per-sentence: <text-file-stem>-<NNNN>.<suffix>
                segment_output = output_dir / f"{text_file.stem}-{global_idx:04d}{audio_suffix}"

                phonetic_label = {
                    "cedict": "拼音(num)", "notone": "拼音(notone)",
                    "tonemark": "拼音(tone)", "ipa": "IPA",
                    "ipa-tones": "IPA(tones)",
                }.get(phonetic.fmt, "拼音")

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
                                logger.info(
                                    f"  [CEDICT]  {d['token']} → {formatted}  ({d['english']})  ⚠ 单字符拼音，保留原字"
                                )
                            else:
                                logger.info(
                                    f"  [CEDICT]  {d['token']} → {formatted}  ({d['english']})"
                                )
                        elif d.get("source") == "passthrough":
                            logger.info(
                                f"  [原字符]  '{d['token']}' (CEDICT 未收录，保留原字符)"
                            )

                if tts_model.synthesize(tts_input, str(segment_output)):
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