#!/usr/bin/env python3
"""
TTS Voice Cloning Script v5.

Uses the IndexTTS vLLM-compatible OpenAI-style audio endpoint shown in
``tests/test-indextts2.py`` while retaining v4 text-file processing features.
"""

import argparse
import base64
import binascii
import glob
import importlib
import json
import mimetypes
import os
import re
import signal
import struct
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
from loguru import logger

from lib.phonetic_converter import PhoneticConverter
from lib.ssml_parser import SSMLParser
from lib.text_segmenter import TextSegmenter

# ---------------------------------------------------------------------------
# Logging and shutdown
# ---------------------------------------------------------------------------


def setup_logging(debug: bool = False):
    logger.remove()

    log_dir = Path("log")
    log_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / f"clone-voice-v5_{timestamp}.log"

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

    console_level = "DEBUG" if debug else "INFO"
    logger.add(
        sys.stderr,
        level=console_level,
        format="<level>{level: <8}</level> | <level>{message}</level>",
        colorize=True,
        enqueue=True,
    )

    logger.info(f"Log file: {log_path}")
    return logger


_shutdown_requested = False


def _signal_handler(signum, frame):
    global _shutdown_requested
    sig_name = signal.Signals(signum).name
    if _shutdown_requested:
        logger.warning(f"Received {sig_name} again, forcing exit")
        sys.exit(1)
    _shutdown_requested = True
    logger.warning(
        f"Received {sig_name}, finishing current sentence then exiting gracefully..."
    )
    logger.warning("Press Ctrl+C again to force quit")


def _install_signal_handlers():
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)


def _build_tts_input(token_details: List[Dict]) -> str:
    parts = []
    for details in token_details:
        token = details["token"]
        formatted = details.get("formatted")
        if not details.get("cedict_match") or formatted is None:
            parts.append(token)
            continue

        pinyin_parts = formatted.split()
        token_chars = list(token)
        if len(formatted) <= 1 or len(token_chars) != len(pinyin_parts):
            parts.append(token)
            continue

        for character, pinyin in zip(token_chars, pinyin_parts):
            parts.append(f"<{character}|{pinyin.upper()}>")

    return "".join(parts)


# ---------------------------------------------------------------------------
# IndexTTS vLLM-compatible request helpers
# ---------------------------------------------------------------------------


def file_to_b64(path: str) -> str:
    with open(path, "rb") as file:
        return base64.b64encode(file.read()).decode()


def load_text(args) -> str:
    if args.text is not None:
        return args.text
    if args.text_file:
        return Path(args.text_file).read_text(encoding="utf-8")
    raise RuntimeError("--text 或 --text-file 必须指定一个")


def audio_to_data_url(path: str) -> str:
    mime, _ = mimetypes.guess_type(path)
    if mime is None:
        mime = "audio/mpeg"
    with open(path, "rb") as file:
        encoded = base64.b64encode(file.read()).decode()
    return f"data:{mime};base64,{encoded}"


def normalize_ref_audio(value: str) -> str:
    if value.startswith(("http://", "https://", "data:", "file://")):
        return value
    return audio_to_data_url(value)


def build_payload(args, text: Optional[str] = None) -> Dict:
    payload = {
        "input": load_text(args) if text is None else text,
        "model": args.model,
        "voice": args.voice,
        "instructions": args.instructions,
        "response_format": args.response_format,
        "speed": args.speed,
        "stream_format": args.stream_format,
        "stream": args.stream,
        "task_type": args.task_type,
        "language": args.language,
        "duration_seconds": args.duration_seconds,
        "x_vector_only_mode": args.x_vector_only_mode,
        "max_new_tokens": args.max_new_tokens,
        "seed": args.seed,
        "initial_codec_chunk_frames": args.initial_codec_chunk_frames,
        "non_streaming_mode": args.non_streaming_mode,
        "word_timestamps": args.word_timestamps,
    }

    if args.ref_audio:
        payload["ref_audio"] = normalize_ref_audio(args.ref_audio)
    if args.ref_audio_2:
        payload["ref_audio_2"] = normalize_ref_audio(args.ref_audio_2)
    if args.ref_text:
        payload["ref_text"] = args.ref_text
    if args.ambient_sound:
        payload["ambient_sound"] = args.ambient_sound
    if args.speaker_embedding:
        payload["speaker_embedding"] = args.speaker_embedding
    if args.extra_json:
        payload["extra_params"] = json.loads(args.extra_json)

    return payload


def _repair_wav_header(audio: bytes) -> bytes:
    if len(audio) < 44 or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
        return audio

    chunk_offset = 12
    while chunk_offset + 8 <= len(audio):
        chunk_id = audio[chunk_offset : chunk_offset + 4]
        chunk_size = struct.unpack_from("<I", audio, chunk_offset + 4)[0]
        if chunk_id == b"data":
            break
        if chunk_size == 0xFFFFFFFF:
            break
        chunk_offset += 8 + chunk_size + (chunk_size & 1)
    else:
        chunk_offset = -1

    if chunk_offset < 0 or audio[chunk_offset : chunk_offset + 4] != b"data":
        raise RuntimeError("SSE 音频中没有找到 WAV data 块")

    riff_size = len(audio) - 8
    data_size = len(audio) - chunk_offset - 8
    if riff_size > 0xFFFFFFFF or data_size > 0xFFFFFFFF:
        raise RuntimeError("WAV 音频超过 RIFF 格式支持的大小")

    repaired = bytearray(audio)
    struct.pack_into("<I", repaired, 4, riff_size)
    struct.pack_into("<I", repaired, chunk_offset + 4, data_size)
    return bytes(repaired)


def extract_sse_audio(content: bytes) -> bytes:
    audio_chunks = []
    saw_sse_data = False

    for raw_line in content.splitlines():
        if not raw_line.startswith(b"data:"):
            continue

        saw_sse_data = True
        data = raw_line[5:].strip()
        if not data or data == b"[DONE]":
            continue

        try:
            event = json.loads(data)
        except json.JSONDecodeError as error:
            raise RuntimeError("SSE data 不是有效 JSON") from error

        if event.get("type") != "speech.audio.delta":
            continue

        audio_base64 = event.get("audio")
        if not audio_base64:
            continue

        try:
            audio_chunks.append(base64.b64decode(audio_base64, validate=True))
        except (binascii.Error, ValueError) as error:
            raise RuntimeError("SSE 音频字段不是有效 Base64") from error

    if not saw_sse_data:
        return content
    if not audio_chunks:
        raise RuntimeError("SSE 响应中没有 speech.audio.delta 音频")
    return _repair_wav_header(b"".join(audio_chunks))


def save_response(response, output: str) -> Path:
    content = extract_sse_audio(response.content)
    output_path = Path(output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(content)
    return output_path


def _validate_reference(value: Optional[str], option_name: str):
    if not value or value.startswith(("http://", "https://", "data:", "file://")):
        return
    if not os.path.exists(value):
        raise FileNotFoundError(f"{option_name} file not found: {value}")


class IndexTTS2API:
    """Client for the IndexTTS vLLM-compatible audio endpoint."""

    def __init__(self, args):
        self.args      = args
        self.url       = args.host.rstrip("/") + "/" + args.path.lstrip("/")
        self.tts_model = getattr(args, "tts_model", None)
        self.timeout   = args.timeout
        _validate_reference(args.ref_audio, "--ref-audio")
        _validate_reference(args.ref_audio_2, "--ref-audio-2")


    def synthesize(self, text: str, output_path: str) -> bool:
        start_time = time.time()
        try:
            payload = build_payload(self.args, text)
            text_length = len(text)

            logger.info("--- TTS API Request ---")
            logger.info(f"  [文本]      {text}")
            logger.info(f"  [文本长度]  {text_length} chars")
            logger.info(f"  [模型]      {self.args.model}")
            logger.info(f"  [语言]      {self.args.language}")
            logger.info(f"  [参考音频]  {self.args.ref_audio or '(none)'}")
            logger.info(f"  [POST]      {self.url}")
            logger.debug(json.dumps(payload, ensure_ascii=False, indent=2))

            response = requests.post(
                self.url,
                json=payload,
                timeout=self.timeout,
            )

            if response.status_code != 200:
                logger.error(f"API returned HTTP {response.status_code}")
                try:
                    logger.error(f"  Detail: {response.json()}")
                except Exception:
                    logger.error(f"  Body: {response.text[:500]}")
                return False

            saved_path = save_response(response, output_path)
            elapsed_time = time.time() - start_time
            file_size = saved_path.stat().st_size
            logger.success("Audio synthesis completed!")
            logger.info(f"  [输出]  {saved_path}")
            logger.info(f"  [大小]  {file_size:,} bytes")
            logger.info(f"  [耗时]  {elapsed_time:.2f}s")
            if elapsed_time > 0:
                logger.info(f"  [速率]  {text_length / elapsed_time:.1f} chars/sec")
            return True
        except Exception as error:
            elapsed_time = time.time() - start_time
            logger.error(f"Synthesis failed: {error}")
            logger.error(f"Time elapsed: {elapsed_time:.2f}s")
            logger.debug("".join(__import__("traceback").format_exception(error)))
            return False


    def synthesize2(self, text: str, output_path: str) -> bool:
        start_time = time.time()
        try:
            if self.tts_model is None:
                raise RuntimeError("Local IndexTTS2 model is not initialized")
            payload = build_payload(self.args, text)
            text_length = len(text)

            logger.info("--- TTS API Request ---")
            logger.info(f"  [文本]      {text}")
            logger.info(f"  [文本长度]  {text_length} chars")
            logger.info(f"  [模型]      {self.args.model}")
            logger.info(f"  [语言]      {self.args.language}")
            logger.info(f"  [参考音频]  {self.args.ref_audio or '(none)'}")
            logger.debug(json.dumps(payload, ensure_ascii=False, indent=2))


            # tts = IndexTTS2(cfg_path="/app/models/tts_models/IndexTeam/IndexTTS-2.5/config.yaml",
            #                 model_dir="/app/models/tts_models/IndexTeam/IndexTTS-2.5"
            #                 )


            self.tts_model.infer(spk_audio_prompt = self.args.ref_audio, 
                      text             = text, 
                      lang             = self.args.language, 
                      output_path      = output_path, 
                      verbose          = True
                      )

            elapsed_time = time.time() - start_time
            file_size = Path(output_path).stat().st_size
            logger.success("Audio synthesis completed!")
            logger.info(f"  [输出]  {output_path}")
            logger.info(f"  [大小]  {file_size:,} bytes")
            logger.info(f"  [耗时]  {elapsed_time:.2f}s")
            if elapsed_time > 0:
                logger.info(f"  [速率]  {text_length / elapsed_time:.1f} chars/sec")
            return True
        except Exception as error:
            elapsed_time = time.time() - start_time
            logger.error(f"Synthesis failed: {error}")
            logger.error(f"Time elapsed: {elapsed_time:.2f}s")
            logger.debug("".join(__import__("traceback").format_exception(error)))
            return False

# ---------------------------------------------------------------------------
# Text processing
# ---------------------------------------------------------------------------


def split_sentences(
    text: str, max_new_tokens: Optional[int] = None
) -> List[str]:
    pattern = r"[^。！？\.\!\?\n]+[。！？\.\!\?]?[\'\"）\]\》」』]?"
    raw = re.findall(pattern, text)

    sentences = []
    for sentence in raw:
        sentence = sentence.strip()
        if sentence:
            sentences.append(sentence)

    if not sentences and text.strip():
        sentences = [text.strip()]

    if not max_new_tokens or max_new_tokens <= 0:
        return sentences

    split_chars = "，,；;、：:"
    limited_sentences = []
    current_sentence = ""

    def append_piece(piece: str):
        nonlocal current_sentence
        if not piece:
            return
        if not current_sentence:
            current_sentence = piece
        elif len(current_sentence) + len(piece) <= max_new_tokens:
            current_sentence += piece
        else:
            limited_sentences.append(current_sentence)
            current_sentence = piece

    for sentence in sentences:
        remaining = sentence
        while len(remaining) > max_new_tokens:
            punctuation_positions = [
                remaining.rfind(char, 0, max_new_tokens)
                for char in split_chars
            ]
            cut_at = max(punctuation_positions)
            if cut_at >= 0:
                cut_end = cut_at + 1
            else:
                whitespace_at = remaining.rfind(" ", 0, max_new_tokens + 1)
                cut_end = whitespace_at if whitespace_at > 0 else max_new_tokens

            append_piece(remaining[:cut_end].strip())
            remaining = remaining[cut_end:].strip()

        if remaining:
            append_piece(remaining)

    if current_sentence:
        limited_sentences.append(current_sentence)

    return limited_sentences


def expand_text_files(pattern: str) -> List[Path]:
    if not pattern.lower().endswith(".txt"):
        raise ValueError("File pattern must end with .txt")

    if "*" in pattern or "?" in pattern:
        matched_files = glob.glob(pattern, recursive=False)
        text_files = []
        for file_path in matched_files:
            path = Path(file_path)
            if path.exists() and path.suffix.lower() == ".txt":
                text_files.append(path)
        text_files.sort()
        return text_files

    path = Path(pattern)
    if path.exists() and path.suffix.lower() == ".txt":
        return [path]
    return []


def _prepare_phonetic(args) -> Optional[PhoneticConverter]:
    if not args.phonetic:
        return None

    logger.info("--- Phonetic Preprocessing ---")
    logger.info(f"Mode: Chinese text -> {args.phonetic_format} format")
    phonetic = PhoneticConverter(
        language="cmn-Hans",
        fmt=args.phonetic_format,
    )
    loaded_path = phonetic.load_cc_cedict(args.cedict)
    logger.success(
        f"Phonetic converter ready (format: {args.phonetic_format}, "
        f"dictionary: {loaded_path})"
    )
    return phonetic


def _tts_input(text: str, phonetic: Optional[PhoneticConverter]):
    if not phonetic or not phonetic.is_loaded:
        return text, None, None
    try:
        phonetic_text, details = phonetic.convert(text)
        return _build_tts_input(details), phonetic_text, details
    except Exception as error:
        logger.warning(f"Phonetic conversion failed: {error}")
        return text, None, None


def _log_phonetic_details(details: Optional[List[Dict]]):
    if not details:
        return
    for item in details:
        if item.get("cedict_match"):
            formatted = item.get("formatted", "")
            if len(formatted) <= 1:
                logger.info(
                    f"  [CEDICT]  {item['token']} -> {formatted} "
                    f"({item['english']})  单字符拼音，保留原字"
                )
            else:
                logger.info(
                    f"  [CEDICT]  {item['token']} -> {formatted} "
                    f"({item['english']})"
                )
        elif item.get("source") == "passthrough":
            logger.info(f"  [原字符]  '{item['token']}' (CEDICT 未收录，保留原字符)")
            pass


def _response_suffix(response_format: str) -> str:
    return {
        "wav": ".wav",
        "mp3": ".mp3",
        "flac": ".flac",
        "pcm": ".pcm",
    }.get(response_format, ".wav")


def _batch_output_settings(output: str, response_format: str):
    output_path = Path(output)
    audio_suffix = output_path.suffix or _response_suffix(response_format)
    output_dir = output_path.parent if output_path.suffix else output_path
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir, audio_suffix


def _process_direct_text(
    text: str,
    output: str,
    tts_api: IndexTTS2API,
    phonetic: Optional[PhoneticConverter],
) -> Tuple[int, int, bool]:
    ssml_parser = SSMLParser()
    if ssml_parser.is_ssml(text):
        logger.info("Detected SSML format")
        text = ssml_parser.extract_text_from_ssml(text)
        logger.info(f"Extracted plain text length: {len(text)} characters")

    tts_input, phonetic_text, details = _tts_input(text, phonetic)
    logger.info(f"[原文]  {text}")
    if phonetic_text is not None:
        logger.info(f"[拼音]  {phonetic_text}")
    logger.info(f"[-> TTS] {tts_input}")
    # _log_phonetic_details(details)

    if _shutdown_requested:
        return 0, 1, True
    success = tts_api.synthesize2(tts_input, output)
    if success:
        logger.success(f"Synthesis succeeded: {output}")
        return 1, 1, False
    logger.error(f"Synthesis failed: {output}")
    return 0, 1, False


def _process_text_file(
    text_file: Path,
    args,
    tts_api: IndexTTS2API,
    phonetic: Optional[PhoneticConverter],
) -> Tuple[int, int, bool]:
    try:
        text = text_file.read_text(encoding="utf-8")
    except Exception as error:
        logger.error(f"Failed to read {text_file}: {error}")
        return 0, 0, False

    logger.info(f"Text length: {len(text)} characters")
    logger.debug(f"Text preview: {text[:120]}...")

    output_dir, audio_suffix = _batch_output_settings(args.output, args.response_format)
    ssml_parser = SSMLParser()
    if ssml_parser.is_ssml(text):
        logger.info("Detected SSML format")
        plain_text = ssml_parser.extract_text_from_ssml(text)
        logger.info(f"Extracted plain text length: {len(plain_text)} characters")

        max_tokens = 4096
        is_valid, error_message = ssml_parser.validate_ssml(text, max_tokens)
        if not is_valid:
            logger.warning(
                f"{error_message} - SSML text is too long, processing in parts"
            )

        segments = TextSegmenter().segment_text(
            plain_text, max_tokens, use_cpu_mode=False
        )
        logger.info(f"Text segmented into {len(segments)} parts")
        file_success = 0
        interrupted = False
        for index, text_segment in enumerate(segments):
            if _shutdown_requested:
                interrupted = True
                break
            segment_output = output_dir / f"{text_file.stem}-{index + 1:04d}{audio_suffix}"
            logger.info(
                f"Synthesizing segment {index + 1}/{len(segments)} "
                f"(len={len(text_segment)}) -> {segment_output}"
            )
            if tts_api.synthesize2(text_segment, str(segment_output)):
                file_success += 1
        return file_success, len(segments), interrupted

    all_sentences = split_sentences(text, max_new_tokens=args.max_new_tokens)
    sentence_count = len(all_sentences)
    logger.info(f"Sentence-based segmentation: {sentence_count} sentences total")

    start = args.start
    end = args.end
    start_index = start - 1 if start > 0 else sentence_count + start
    end_index = end if end > 0 else sentence_count + end + 1
    start_index = max(0, min(start_index, sentence_count))
    end_index = max(0, min(end_index, sentence_count))

    if start_index >= end_index:
        logger.error(
            f"Invalid sentence range: start={start}, end={end} "
            f"resolved to [{start_index}:{end_index}] (total {sentence_count})"
        )
        return 0, 0, False

    sentences = all_sentences[start_index:end_index]
    logger.info(
        f"Selected sentences {start}..{end} -> "
        f"indices [{start_index}:{end_index}] -> {len(sentences)} sentence(s)"
    )

    file_success = 0
    interrupted = False
    for index, sentence in enumerate(sentences):
        if _shutdown_requested:
            interrupted = True
            break

        global_index = start_index + index + 1
        tts_input, phonetic_text, details = _tts_input(sentence, phonetic)
        segment_output = output_dir / f"{text_file.stem}-{global_index:04d}{audio_suffix}"

        logger.info(f"-- Sentence {global_index}/{sentence_count} --")
        logger.info(f"  [原文]   {sentence}")
        if phonetic_text is not None:
            logger.info(f"  [拼音]   {phonetic_text}")
        logger.info(f"  [-> TTS] {tts_input}")
        logger.info(f"  [输出]   {segment_output}")
        # _log_phonetic_details(details)

        if tts_api.synthesize2(tts_input, str(segment_output)):
            file_success += 1
            logger.success(f"Sentence {global_index} succeeded")
        else:
            logger.error(f"Sentence {global_index} failed")

    return file_success, len(sentences), interrupted


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="TTS Voice Cloning Script v5 - IndexTTS vLLM API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    text_group = parser.add_mutually_exclusive_group(required=True)
    text_group.add_argument(
        "-t",
        "--text",
        type=str,
        help="Text to synthesize directly",
    )
    text_group.add_argument(
        "-f",
        "--text-file",
        type=str,
        help="Input text file or .txt wildcard for batch processing",
    )

    parser.add_argument(
        "-o",
        "--output",
        default="output.wav",
        help="Output audio file, or output directory for --text-file batch processing",
    )

    parser.add_argument(
        "-H",
        "--host",
        default="http://10.0.13.209:20212",
        help="IndexTTS server host (default: http://10.0.13.209:20212)",
    )
    parser.add_argument(
        "-P",
        "--path",
        default="/v1/audio/speech",
        help="Audio API path (default: /v1/audio/speech)",
    )
    parser.add_argument(
        "-T",
        "--timeout",
        type=int,
        default=1200,
        help="HTTP request timeout in seconds (default: 1200)",
    )

    parser.add_argument("-m", "--model", default="IndexTeam/IndexTTS-2.5")
    parser.add_argument("-v", "--voice", default="default")
    parser.add_argument("-l", "--language", default="zh")
    parser.add_argument("-S", "--speed", type=float, default=1.0)
    parser.add_argument(
        "--response-format",
        default="wav",
        choices=["wav", "mp3", "flac", "pcm"],
    )
    parser.add_argument("--instructions", default="")
    parser.add_argument("--task-type", default="CustomVoice")

    parser.add_argument("-a", "--ref-audio")
    parser.add_argument("-A", "--ref-audio-2")
    parser.add_argument("--ref-text")
    parser.add_argument("--ambient-sound")
    parser.add_argument("--speaker-embedding")

    parser.add_argument("--seed", type=int, default=1234)
    parser.add_argument("--max-new-tokens", type=int, default=500)
    parser.add_argument("--duration-seconds", type=float, default=0)
    parser.add_argument("--initial-codec-chunk-frames", type=int, default=0)

    parser.add_argument("--stream", action="store_true")
    parser.add_argument("--stream-format", default="sse")
    parser.add_argument("--non-streaming-mode", action="store_true")
    parser.add_argument("--word-timestamps", action="store_true")
    parser.add_argument("--x-vector-only-mode", action="store_true")
    parser.add_argument("--extra-json")
    parser.add_argument("-d", "--debug", action="store_true")

    parser.add_argument("--phonetic", action="store_true")
    parser.add_argument(
        "--phonetic-format",
        default="cedict",
        choices=["cedict", "notone", "tonemark", "ipa", "ipa-tones"],
    )
    parser.add_argument("--cedict")

    parser.add_argument(
        "-s",
        "--start",
        type=int,
        default=1,
        help="First sentence for --text-file (1-based; negative counts from the end)",
    )
    parser.add_argument(
        "-e",
        "--end",
        type=int,
        default=-1,
        help="Last sentence for --text-file (inclusive; negative counts from the end)",
    )
    return parser


def main() -> int:
    global _shutdown_requested
    _shutdown_requested = False
    args = build_parser().parse_args()
    setup_logging(debug=args.debug)
    _install_signal_handlers()

    try:
        IndexTTS2 = importlib.import_module("indextts.infer_v2_5").IndexTTS2
    except ImportError as error:
        logger.error(f"Local IndexTTS2 dependencies are unavailable: {error}")
        return 1

    args.tts_model = IndexTTS2(
        cfg_path="/app/models/tts_models/IndexTeam/IndexTTS-2.5/config.yaml",
        model_dir="/app/models/tts_models/IndexTeam/IndexTTS-2.5",
    )

    try:
        tts_api = IndexTTS2API(args)
        phonetic = _prepare_phonetic(args)
    except Exception as error:
        logger.error(f"Initialization failed: {error}")
        return 1

    total_success = 0
    total_segments = 0
    interrupted = False

    try:
        if args.text is not None:
            total_success, total_segments, interrupted = _process_direct_text(
                args.text,
                args.output,
                tts_api,
                phonetic,
            )
        else:
            text_files = expand_text_files(args.text_file)
            if not text_files:
                logger.error(f"No .txt files found matching pattern: {args.text_file}")
                return 1

            logger.info(f"Found {len(text_files)} text file(s) to process")
            for file_index, text_file in enumerate(text_files, 1):
                if _shutdown_requested:
                    interrupted = True
                    break
                logger.info("=" * 60)
                logger.info(
                    f"Processing file {file_index}/{len(text_files)}: {text_file.name}"
                )
                logger.info("=" * 60)
                file_success, file_segments, file_interrupted = _process_text_file(
                    text_file,
                    args,
                    tts_api,
                    phonetic,
                )
                total_success += file_success
                total_segments += file_segments
                if file_interrupted:
                    interrupted = True
                    break
    except KeyboardInterrupt:
        logger.warning("KeyboardInterrupt received, shutting down gracefully")
        interrupted = True

    logger.info("=" * 60)
    logger.info("Summary (interrupted)" if interrupted else "Overall Summary")
    logger.info("=" * 60)
    logger.info(f"Total segments: {total_segments}")
    logger.info(f"Successful segments: {total_success}")
    logger.info(f"Failed segments: {total_segments - total_success}")

    if interrupted:
        logger.warning("Process was interrupted by user signal")
        return 130
    if total_success == total_segments:
        logger.success("All segments synthesized successfully!")
        return 0
    logger.error(f"{total_segments - total_success} segment(s) failed to synthesize")
    return 1


if __name__ == "__main__":
    sys.exit(main())
