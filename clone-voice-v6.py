#!/usr/bin/env python3
"""TTS Voice Cloning Script v6 with multi-format document input."""

import argparse
import base64
import binascii
import glob
import json
import mimetypes
import os
import re
import signal
import struct
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import requests
from loguru import logger

from lib.document_loader import DocumentLoader, DocumentSegment
from lib.phonetic_converter import PhoneticConverter
from lib.ssml_parser import SSMLParser
from lib.text_segmenter import TextSegmenter
# ebf17cc104b44bbb8c0c29e755fb02ba.OlhjHvReKC8L1278

def setup_logging(debug: bool = False):
    logger.remove()

    log_dir = Path("log")
    log_dir.mkdir(exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / f"clone-voice-v6_{timestamp}.log"

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
        f"Received {sig_name}, finishing current segment then exiting gracefully..."
    )
    logger.warning("Press Ctrl+C again to force quit")


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
            parts.append(f"<{character}|{pinyin}>")

    return "".join(parts)


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
        self.args = args
        self.url = args.host.rstrip("/") + "/" + args.path.lstrip("/")
        self.timeout = args.timeout
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

            payload_dump = payload.copy()
            if "ref_audio" in payload_dump:
                payload_dump["ref_audio"] = f"data in {self.args.ref_audio}"
            logger.debug(json.dumps(payload_dump, ensure_ascii=False, indent=2))

            response = requests.post(
                self.url,
                json=payload,
                headers={"Authorization": f"Bearer {self.args.api_key}"},
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

def expand_document_files(pattern: str) -> List[Path]:
    """Expand one supported document path or a wildcard pattern."""
    if glob.has_magic(pattern):
        matched_paths = glob.glob(pattern, recursive=True)
        paths = {
            Path(file_path)
            for file_path in matched_paths
            if Path(file_path).is_file() and DocumentLoader.supports(Path(file_path))
        }
        return sorted(paths, key=lambda path: str(path).lower())

    path = Path(pattern)
    if not path.exists():
        return []
    if not path.is_file():
        return []
    if not DocumentLoader.supports(path):
        raise ValueError(
            f"Unsupported document type: {path.suffix}. "
            f"Supported types: {', '.join(sorted(DocumentLoader.SUPPORTED_SUFFIXES))}"
        )
    return [path]


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


def _response_suffix(response_format: str) -> str:
    return {
        "wav": ".wav",
        "mp3": ".mp3",
        "flac": ".flac",
        "pcm": ".pcm",
    }.get(response_format, ".wav")


def _ensure_output_directory(output_dir: Path) -> Path:
    output_dir = Path(output_dir)
    if output_dir.exists():
        if not output_dir.is_dir():
            raise ValueError(f"输出路径已被同名文件占用，不是目录: {output_dir}")
        return output_dir

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise ValueError(f"输出目录无效或无法创建: {output_dir}: {error}") from error

    if not output_dir.is_dir():
        raise ValueError(f"输出目录无效: {output_dir}")
    return output_dir


def _document_output_directory(output: str) -> Path:
    output_path = Path(output)
    return output_path.parent if output_path.suffix else output_path


def validate_output_path(output: str, document_mode: bool) -> Path:
    """Validate the output shape before loading documents or calling TTS."""
    output_path = Path(output)
    if document_mode:
        return _ensure_output_directory(_document_output_directory(output))

    if output_path.exists() and output_path.is_dir():
        raise ValueError(f"直接合成的输出路径必须是文件，不是目录: {output_path}")

    _ensure_output_directory(output_path.parent)
    return output_path


def _batch_output_settings(output: str, response_format: str):
    output_path = Path(output)
    audio_suffix = output_path.suffix or _response_suffix(response_format)
    output_dir = _document_output_directory(output)
    _ensure_output_directory(output_dir)
    return output_dir, audio_suffix


def _safe_path_component(value: str, fallback: str = "document") -> str:
    component = re.sub(r'[<>:"/\\|?*]+', "_", value).strip(" .")
    return component or fallback


def build_segment_output_paths(
    output_dir: Path,
    document_path: Path,
    segments: Sequence[DocumentSegment],
    response_format: str,
) -> List[Path]:
    """Build output paths, resetting EPUB numbering for each HTML source."""
    output_dir = Path(output_dir)
    _ensure_output_directory(output_dir)

    if Path(document_path).suffix.lower() == ".epub":
        document_dir = output_dir / _safe_path_component(Path(document_path).stem)
        counters: Dict[str, int] = {}
        paths: List[Path] = []
        for segment in segments:
            source_label = str(segment.source_label).replace("\\", "/")
            source_key = source_label
            html_name = _safe_path_component(Path(source_label).stem, "html")
            segment_index = counters.get(source_key, 0)
            counters[source_key] = segment_index + 1
            path = document_dir / html_name / f"audio-{segment_index:03d}.wav"
            path.parent.mkdir(parents=True, exist_ok=True)
            paths.append(path)
        return paths

    suffix = Path(document_path).suffix
    prefix = _safe_path_component(Path(document_path).stem)
    audio_suffix = suffix if suffix and suffix.lower() in {".wav", ".mp3", ".flac", ".pcm"} else _response_suffix(response_format)
    paths = []
    for index, _segment in enumerate(segments, start=1):
        path = output_dir / f"{prefix}-{index:04d}{audio_suffix}"
        path.parent.mkdir(parents=True, exist_ok=True)
        paths.append(path)
    return paths


def _resolve_range(total: int, start: int, end: int) -> Tuple[int, int]:
    start_index = start - 1 if start > 0 else total + start
    end_index = end if end > 0 else total + end + 1
    return (
        max(0, min(start_index, total)),
        max(0, min(end_index, total)),
    )


def select_epub_html_range(
    segments: Sequence[DocumentSegment],
    start: int,
    end: int,
    source_order: Optional[Sequence[str]] = None,
) -> List[DocumentSegment]:
    """Select every segment belonging to EPUB HTML files in an inclusive range."""
    ordered_sources = list(source_order or [])
    if not ordered_sources:
        ordered_sources = [segment.source_label for segment in segments]
    ordered_sources = list(dict.fromkeys(ordered_sources))
    start_index, end_index = _resolve_range(len(ordered_sources), start, end)
    if start_index >= end_index:
        return []

    selected_sources = set(ordered_sources[start_index:end_index])
    return [segment for segment in segments if segment.source_label in selected_sources]


def _select_segment_range(
    segments: Sequence[DocumentSegment],
    start: int,
    end: int,
) -> List[DocumentSegment]:
    start_index, end_index = _resolve_range(len(segments), start, end)
    return list(segments[start_index:end_index]) if start_index < end_index else []


def _write_intermediate_json(
    document_path: Path,
    extracted_text: str,
    segment_entries: Sequence[Dict],
) -> None:
    """For txt/html sources write a same-name JSON capturing the intermediate forms."""
    output_path = Path(document_path).with_suffix(".json")
    body = {
        "text": extracted_text or "",
        "segments": {
            f"{index:03d}": entry
            for index, entry in enumerate(segment_entries, start=1)
        },
    }
    output_path.write_text(
        json.dumps(body, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.success(f"Intermediate JSON written: {output_path}")


def _write_epub_intermediate_json(
    output_dir: Path,
    document_path: Path,
    segments: Sequence,
    segment_entries: Sequence[Dict],
) -> None:
    """For each EPUB HTML part write a JSON next to its audio outputs.

    Location: <output_dir>/<book>/<html_stem>/<html_stem>.json
    """
    document_dir = Path(output_dir) / _safe_path_component(
        Path(document_path).stem
    )
    groups: Dict[str, List[Tuple[object, Dict]]] = {}
    for segment, entry in zip(segments, segment_entries):
        groups.setdefault(segment.source_label, []).append((segment, entry))

    for source_label, items in groups.items():
        html_stem = Path(source_label).stem
        html_dir = _safe_path_component(html_stem, "html")
        output_path = document_dir / html_dir / f"{html_stem}.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        body = {
            "text": "\n\n".join(segment.text for segment, _ in items),
            "segments": {
                f"{index:03d}": entry
                for index, (_, entry) in enumerate(items, start=1)
            },
        }
        output_path.write_text(
            json.dumps(body, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.success(f"Intermediate JSON written: {output_path}")


def _process_direct_text(
    text: str,
    output: str,
    tts_api: IndexTTS2API,
    phonetic: Optional[PhoneticConverter],
    skip_tts: bool = False,
) -> Tuple[int, int, bool]:
    ssml_parser = SSMLParser()
    if ssml_parser.is_ssml(text):
        logger.info("Detected SSML format")
        text = ssml_parser.extract_text_from_ssml(text)
        logger.info(f"Extracted plain text length: {len(text)} characters")

    tts_input, phonetic_text, _details = _tts_input(text, phonetic)
    logger.info(f"[原文]  {text}")
    # if phonetic_text is not None:
    #     logger.info(f"[拼音]  {phonetic_text}")
    logger.info(f"[-> TTS] {tts_input}")

    if _shutdown_requested:
        return 0, 1, True
    if skip_tts:
        logger.success("Split ok (skip TTS)")
        return 1, 1, False
    success = tts_api.synthesize(tts_input, output)
    if success:
        logger.success(f"Synthesis succeeded: {output}")
        return 1, 1, False
    logger.error(f"Synthesis failed: {output}")
    return 0, 1, False


def _process_document_file(
    document_path: Path,
    args,
    tts_api: IndexTTS2API,
    phonetic: Optional[PhoneticConverter],
) -> Tuple[int, int, bool]:
    try:
        loader = DocumentLoader(
            max_chars_per_segment=max(40, args.max_new_tokens // 10),
        )
        segments = loader.load_segments(document_path)
    except Exception as error:
        logger.error(f"Failed to load {document_path}: {error}")
        return 0, 0, False

    if document_path.suffix.lower() == ".epub":
        html_sources = list(getattr(loader, "last_source_order", []) or [])
        if not html_sources:
            html_sources = list(
                dict.fromkeys(segment.source_label for segment in segments)
            )
        selected_segments = select_epub_html_range(
            segments,
            start        = args.start,
            end          = args.end,
            source_order = html_sources,
        )
        start_index, end_index = _resolve_range(
            len(html_sources), args.start, args.end
        )
        logger.info(
            f"EPUB HTML files: {len(html_sources)} total, "
            f"selected {args.start}..{args.end} -> "
            f"indices [{start_index + 1}:{end_index}] -> "
            f"{len(dict.fromkeys(segment.source_label for segment in selected_segments))} file(s)"
        )
    else:
        selected_segments = _select_segment_range(
            segments,
            start = args.start,
            end   = args.end,
        )
        logger.info(
            f"Document segments: {len(segments)} total, "
            f"selected {len(selected_segments)}"
        )

    if not selected_segments:
        logger.error(
            f"No segments selected from {document_path} for range "
            f"{args.start}..{args.end}"
        )
        return 0, 0, False

    output_dir, _audio_suffix = _batch_output_settings(
        args.output,
        args.response_format,
    )
    output_paths = build_segment_output_paths(
        output_dir,
        document_path,
        selected_segments,
        args.response_format,
    )

    file_success = 0
    interrupted = False
    segment_entries: List[Dict] = []
    for index, (segment, output_path) in enumerate(
        zip(selected_segments, output_paths),
        start=1,
    ):
        if _shutdown_requested:
            interrupted = True
            break

        tts_input, phonetic_text, _details = _tts_input(segment.text, phonetic)
        segment_entries.append(
            {
                "text": segment.text,
                "phonetic": tts_input,
            }
        )
        logger.info(
            f"-- Segment {index}/{len(selected_segments)} "
            f"({segment.source_label}) --"
        )
        logger.info(f"  [原文]   {segment.text}")
        # if phonetic_text is not None:
        #     logger.info(f"  [拼音]   {phonetic_text}")
        logger.info(f"  [-> TTS] {tts_input}")
        logger.info(f"  [输出]   {output_path}")

        if args.skip_tts:
            file_success += 1
            logger.success(f"Segment {index} split ok (skip TTS)")
        elif tts_api.synthesize(tts_input, str(output_path)):
            file_success += 1
            logger.success(f"Segment {index} succeeded")
        else:
            logger.error(f"Segment {index} failed")

    if document_path.suffix.lower() == ".epub":
        _write_epub_intermediate_json(
            output_dir,
            document_path,
            selected_segments,
            segment_entries,
        )
    else:
        single_text_formats = {".txt", ".md", ".markdown", ".html", ".htm", ".xhtml"}
        if document_path.suffix.lower() in single_text_formats:
            extracted_text = getattr(loader, "last_extracted_text", None) or ""
        else:
            extracted_text = "\n\n".join(
                segment.text for segment in selected_segments
            )
        _write_intermediate_json(
            document_path,
            extracted_text,
            segment_entries,
        )

    return file_success, len(selected_segments), interrupted


_process_text_file = _process_document_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="TTS Voice Cloning Script v6 - multi-format document input",
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
        help="Document path or wildcard (.txt, .md, .markdown, .epub, .pdf, .docx, .html, .htm, .xhtml)",
    )

    parser.add_argument(
        "-o",
        "--output",
        default="output.wav",
        help="Output audio file, or output directory for document processing",
    )
    parser.add_argument(
        "-H",
        "--host",
        default="http://10.0.13.209:20213",
        help="IndexTTS server host (default: http://10.0.13.209:20213)",
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
    parser.add_argument("-K", "--api-key", default="sk-indextts-v2_5_20260902")
    parser.add_argument("--ref-text")
    parser.add_argument("--ambient-sound")
    parser.add_argument("--speaker-embedding")

    parser.add_argument("--seed", type=int, default=1234)
    parser.add_argument("--max-new-tokens", type=int, default=1000)
    parser.add_argument("--duration-seconds", type=float, default=0)
    parser.add_argument("--initial-codec-chunk-frames", type=int, default=0)

    parser.add_argument("--stream", action="store_true")
    parser.add_argument("--stream-format", default="sse")
    parser.add_argument("--non-streaming-mode", action="store_true")
    parser.add_argument("--word-timestamps", action="store_true")
    parser.add_argument("--x-vector-only-mode", action="store_true")
    parser.add_argument("--extra-json")
    parser.add_argument("--skip-tts", action="store_true",
                        help="Only segment text; do not call the TTS API (for split testing)")
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
        help="First EPUB HTML file or document segment (1-based; negative counts from the end)",
    )
    parser.add_argument(
        "-e",
        "--end",
        type=int,
        default=-1,
        help="Last EPUB HTML file or document segment, inclusive",
    )
    return parser


def main() -> int:
    global _shutdown_requested
    _shutdown_requested = False
    args = build_parser().parse_args()
    setup_logging(debug=args.debug)
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    try:
        validate_output_path(args.output, document_mode=args.text is None)
    except ValueError as error:
        logger.error(str(error))
        return 1

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
                skip_tts=args.skip_tts,
            )
        else:
            try:
                document_files = expand_document_files(args.text_file)
            except ValueError as error:
                logger.error(str(error))
                return 1

            if not document_files:
                logger.error(
                    f"No supported document files found matching: {args.text_file}"
                )
                return 1

            logger.info(f"Found {len(document_files)} document file(s) to process")
            for file_index, document_path in enumerate(document_files, 1):
                if _shutdown_requested:
                    interrupted = True
                    break
                logger.info("=" * 60)
                logger.info(
                    f"Processing file {file_index}/{len(document_files)}: "
                    f"{document_path.name}"
                )
                logger.info("=" * 60)
                file_success, file_segments, file_interrupted = _process_document_file(
                    document_path,
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