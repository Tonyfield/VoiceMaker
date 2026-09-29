"""Load supported document formats and split their text for TTS callers."""

from __future__ import annotations

import re
import posixpath
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Iterable, List, Optional
from urllib.parse import unquote
from xml.etree import ElementTree

from bs4 import BeautifulSoup
from loguru import logger

from src.exceptions import TextProcessingError

try:
    from ebooklib import ITEM_DOCUMENT, epub
except ImportError:  # Keep plain-text loading importable without EbookLib.
    ITEM_DOCUMENT = object()
    epub = SimpleNamespace(read_epub=None)

# Sentence-ending punctuation: a merged line already ending with one of these
# does not need any separator appended.
TERMINAL_PUNCTUATION = "。！？!?.…"


class _ZipEpubItem:
    def __init__(self, file_name: str, content: bytes) -> None:
        self.file_name = file_name
        self._content = content

    def get_content(self) -> bytes:
        return self._content


def _recombine_delimited(parts: List[str]) -> List[str]:
    """Rejoin adjacent content/delimiter pairs from a capturing re.split."""
    units = []
    for index in range(0, len(parts) - 1, 2):
        unit = parts[index] + parts[index + 1]
        if unit.strip():
            units.append(unit)
    if len(parts) % 2 == 1:
        tail = parts[-1].strip()
        if tail:
            units.append(tail)
    return units


@dataclass
class DocumentSegment:
    """Normalized text segment and the source it came from."""

    segment_id: str
    text: str
    title: str
    source_label: str
    estimated_duration: float

    def to_dict(self) -> dict:
        """Convert the segment to a JSON-serializable dictionary."""
        return asdict(self)


class DocumentLoader:
    """Load supported document formats without performing TTS work."""

    SUPPORTED_SUFFIXES = {
        ".txt",
        ".md",
        ".markdown",
        ".epub",
        ".pdf",
        ".docx",
        ".html",
        ".htm",
        ".xhtml",
    }

    def __init__(
        self,
        max_chars_per_segment: int = 280,
        max_estimated_duration_seconds: float = 30.0,
        max_tokens_per_segment: Optional[int] = None,
        token_estimator: Optional[Callable[[str], int]] = None,
        force_chunk_chars: Optional[int] = None,
    ) -> None:
        self.max_chars_per_segment = max_chars_per_segment
        self.max_estimated_duration_seconds = max_estimated_duration_seconds
        self.max_tokens_per_segment = max_tokens_per_segment
        self._token_estimator = token_estimator or self._estimate_default_tokens
        self._force_chunk_chars = max(
            1,
            int(force_chunk_chars or max(40, max_chars_per_segment // 2)),
        )
        self.last_source_order: List[str] = []
        self.last_extracted_text: str = ""

    @classmethod
    def supports(cls, file_path: Path) -> bool:
        """Return whether ``file_path`` has a supported document suffix."""
        return Path(file_path).suffix.lower() in cls.SUPPORTED_SUFFIXES

    def load_segments(self, file_path: Path) -> List[DocumentSegment]:
        """Read ``file_path`` and return normalized text segments."""
        file_path = Path(file_path)
        self.last_source_order = []
        if not self.supports(file_path):
            raise TextProcessingError(
                f"Unsupported document type: {file_path.suffix}",
                {"supported": sorted(self.SUPPORTED_SUFFIXES)},
            )

        suffix = file_path.suffix.lower()
        if suffix in {".txt", ".md", ".markdown"}:
            text = self._load_text_document(file_path)
            return self._split_document_text(
                text,
                title=file_path.stem,
                source_label=file_path.name,
            )

        if suffix in {".html", ".htm", ".xhtml"}:
            text = self._html_to_text(
                file_path.read_text(encoding="utf-8", errors="ignore")
            )
            return self._split_document_text(
                text,
                title=file_path.stem,
                source_label=file_path.name,
            )

        if suffix == ".epub":
            return self._load_epub_segments(file_path)
        if suffix == ".pdf":
            return self._load_pdf_segments(file_path)
        if suffix == ".docx":
            return self._load_docx_segments(file_path)

        raise TextProcessingError(f"No loader available for {file_path.suffix}")

    def _load_text_document(self, file_path: Path) -> str:
        raw_text = file_path.read_text(encoding="utf-8", errors="ignore")
        if file_path.suffix.lower() in {".md", ".markdown"}:
            return self._strip_markdown(raw_text)
        return raw_text

    def _load_epub_segments(self, file_path: Path) -> List[DocumentSegment]:
        segments: List[DocumentSegment] = []
        items = list(self._iter_epub_items(file_path))
        self.last_source_order = [str(item.file_name) for item in items]

        for item in items:
            content = item.get_content().decode("utf-8", errors="ignore")
            text = self._html_to_text(content)
            if not text:
                continue

            source_label = str(item.file_name)
            title = self._extract_html_title(content) or Path(source_label).stem
            segments.extend(
                self._split_document_text(
                    text,
                    title=title,
                    source_label=source_label,
                )
            )

        return self._renumber_segments(file_path.stem, segments)

    def _iter_epub_items(self, file_path: Path) -> Iterable[_ZipEpubItem]:
        if epub.read_epub is not None:
            book = epub.read_epub(str(file_path))
            return book.get_items_of_type(ITEM_DOCUMENT)
        return self._read_epub_zip_items(file_path)

    def _read_epub_zip_items(self, file_path: Path) -> List[_ZipEpubItem]:
        with zipfile.ZipFile(file_path) as archive:
            try:
                container = ElementTree.fromstring(
                    archive.read("META-INF/container.xml")
                )
                rootfile = next(
                    element
                    for element in container.iter()
                    if element.tag.rsplit("}", 1)[-1] == "rootfile"
                )
                opf_path = posixpath.normpath(rootfile.attrib["full-path"])
                package = ElementTree.fromstring(archive.read(opf_path))
            except (KeyError, StopIteration, ElementTree.ParseError) as exc:
                raise TextProcessingError(
                    f"Invalid EPUB container or package: {file_path}"
                ) from exc

            manifest: dict[str, dict[str, str]] = {}
            spine_ids: List[str] = []
            for element in package.iter():
                tag = element.tag.rsplit("}", 1)[-1]
                if tag == "item" and element.attrib.get("id"):
                    manifest[element.attrib["id"]] = dict(element.attrib)
                elif tag == "itemref" and element.attrib.get("idref"):
                    spine_ids.append(element.attrib["idref"])

            ordered_items = [manifest[item_id] for item_id in spine_ids if item_id in manifest]
            if not ordered_items:
                ordered_items = list(manifest.values())

            items: List[_ZipEpubItem] = []
            opf_dir = posixpath.dirname(opf_path)
            for item in ordered_items:
                if item.get("media-type") not in {"application/xhtml+xml", "text/html"}:
                    continue
                href = unquote(item.get("href", "")).split("#", 1)[0]
                content_path = posixpath.normpath(posixpath.join(opf_dir, href))
                if content_path not in archive.namelist():
                    continue
                items.append(_ZipEpubItem(content_path, archive.read(content_path)))
            return items

    def _load_pdf_segments(self, file_path: Path) -> List[DocumentSegment]:
        try:
            import fitz
        except ImportError as exc:
            raise TextProcessingError("PyMuPDF is required for PDF support") from exc

        segments: List[DocumentSegment] = []
        with fitz.open(file_path) as document:
            for page_number, page in enumerate(document, start=1):
                text = self._clean_text(page.get_text("text"))
                if not text:
                    continue
                title = f"{file_path.stem} page {page_number}"
                segments.extend(
                    self._split_document_text(
                        text,
                        title=title,
                        source_label=f"page-{page_number}",
                    )
                )

        return self._renumber_segments(file_path.stem, segments)

    def _load_docx_segments(self, file_path: Path) -> List[DocumentSegment]:
        try:
            from docx import Document
        except ImportError as exc:
            raise TextProcessingError(
                "python-docx is required for DOCX support"
            ) from exc

        document = Document(file_path)
        paragraphs = [
            paragraph.text
            for paragraph in document.paragraphs
            if paragraph.text.strip()
        ]
        return self._split_document_text(
            "\n\n".join(paragraphs),
            title=file_path.stem,
            source_label=file_path.name,
        )

    def _extract_html_title(self, html: str) -> Optional[str]:
        soup = BeautifulSoup(html, "html.parser")
        heading = soup.find(["h1", "h2", "title"])
        if heading and heading.get_text(strip=True):
            return heading.get_text(strip=True)
        return None

    def _html_to_text(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        body = soup.body
        if body is None:
            return ""

        for tag in body.find_all(["script", "style", "noscript"]):
            tag.decompose()
        for tag in body.find_all("p", class_="notecontent"):
            tag.decompose()
        for tag in body.find_all("a"):
            visible_text = self._clean_text(tag.get_text(" ", strip=True))
            if re.fullmatch(r"\[\d+\]", visible_text):
                tag.decompose()

        # Convert block-level elements to newline boundaries so the original
        # paragraph (回车) information is kept instead of being flattened to
        # spaces. Each block/line break becomes at least one "\n".
        block_tags = [
            "p", "div", "section", "article", "header", "footer", "aside",
            "blockquote", "pre", "table", "ul", "ol", "li", "dd", "dt",
            "tr", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6", "br",
        ]
        for tag in body.find_all(block_tags):
            tag.append("\n")

        text = self._clean_text(body.get_text(" "))
        references = re.findall(r"\[\d+\]", text)
        if references:
            logger.warning(
                "Removed {} standalone numeric reference(s) from HTML body: {}",
                len(references),
                ", ".join(references),
            )
            text = re.sub(r"\[\d+\]", "", text)
        return self._clean_text(text)

    def _strip_markdown(self, markdown_text: str) -> str:
        text = re.sub(r"```.*?```", " ", markdown_text, flags=re.DOTALL)
        text = re.sub(r"`([^`]*)`", r"\1", text)
        text = re.sub(r"!\[[^\]]*\]\([^\)]*\)", " ", text)
        text = re.sub(r"\[([^\]]+)\]\([^\)]*\)", r"\1", text)
        text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"[*_~>#-]", " ", text)
        return self._clean_text(text)

    def _split_document_text(
        self,
        text: str,
        title: str,
        source_label: str,
    ) -> List[DocumentSegment]:
        cleaned = self._clean_text(text)
        self.last_extracted_text = cleaned
        if not cleaned:
            return []

        # Each source line (separated by "\n") is kept as a whole unit. This
        # preserves the original回车, and prevents a long line (e.g. a dialogue
        # sentence) from being glued to the lines above/below it (narration).
        # Adjacent lines may still merge while within the limits; at every merge
        # the previous line gets a comma appended (unless it already ends with
        # sentence-ending punctuation) so TTS still pauses at the join.
        chunks: List[str] = []
        current = ""
        for line in cleaned.split("\n"):
            line = line.strip()
            if not line:
                continue

            # A single line alone exceeding the limits is force-split. Only its
            # FIRST parts become separate segments; the LAST part stays in
            # `current` so it can still merge with the following lines.
            if self._would_exceed_limits(line):
                if current:
                    chunks.append(current)
                    current = ""
                parts = self._force_split(line)
                if not parts:
                    continue
                chunks.extend(parts[:-1])
                current = parts[-1]
                continue

            candidate = f"{current}\n{line}" if current else line
            if current and self._would_exceed_limits(candidate):
                chunks.append(current)
                current = line
            elif current:
                if self._needs_comma(current):
                    current = f"{current}，"
                current = f"{current}\n{line}"
            else:
                current = line

        if current:
            chunks.append(current)

        return [
            DocumentSegment(
                segment_id=self._build_segment_id(title, index),
                text=chunk,
                title=title,
                source_label=source_label,
                estimated_duration=round(self._estimate_duration(chunk), 2),
            )
            for index, chunk in enumerate(chunks, start=1)
        ]

    @staticmethod
    def _needs_comma(text: str) -> bool:
        """True when a merged line lacks sentence-ending punctuation.

        Quotes count as lacking it, so a line ending with a quote also gets a
        comma appended.
        """
        stripped = text.rstrip()
        return bool(stripped) and stripped[-1] not in TERMINAL_PUNCTUATION

    def _split_sentences(self, text: str) -> List[str]:
        parts = re.split(r"(?<=[。！？!?\.])\s*", text)
        if len(parts) == 1:
            return [text]
        return [part.strip() for part in parts if part.strip()]

    def _would_exceed_limits(self, text: str) -> bool:
        token_limit_exceeded = (
            self.max_tokens_per_segment is not None
            and self._token_estimator(text) > self.max_tokens_per_segment
        )
        return (
            len(text) > self.max_chars_per_segment
            or self._estimate_duration(text) > self.max_estimated_duration_seconds
            or token_limit_exceeded
        )

    def _estimate_duration(self, text: str) -> float:
        chinese_chars = sum(
            1 for character in text if "\u4e00" <= character <= "\u9fff"
        )
        latin_words = len(re.findall(r"[A-Za-z0-9']+", text))

        if chinese_chars and chinese_chars >= max(1, latin_words * 2):
            return chinese_chars / 4.0
        if latin_words:
            return (latin_words / 150) * 60
        return max(len(text) / 12.0, 1.0)

    @staticmethod
    def _estimate_default_tokens(text: str) -> int:
        """Estimate tokens by counting non-whitespace characters."""
        return sum(1 for character in text if not character.isspace())

    @staticmethod
    def _clean_text(text: str) -> str:
        """Normalize horizontal whitespace but keep line breaks (paragraphs)."""
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", text)
        text = re.sub(r"[ \t\v\f]+", " ", text)
        text = re.sub(r" *\n *", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _force_split(self, text: str) -> List[str]:
        units = self._chunkable_units(text)
        chunks: List[str] = []
        current = ""

        for unit in units:
            candidate = f"{current} {unit}".strip() if current else unit
            if current and self._would_exceed_limits(candidate):
                chunks.append(current)
                current = unit
            else:
                current = candidate

        if current:
            chunks.append(current)
        return chunks

    def _chunkable_units(self, text: str) -> Iterable[str]:
        # Prefer sentence/punctuation boundaries so a long quoted line is broken
        # into semantically self-contained pieces (keeping quote content and its
        # closing quote together) instead of being arbitrarily character-chunked.
        parts = re.split(r"([。！？!?]+[”’」』\"]*)", text)
        sentence_parts = _recombine_delimited(parts)
        if len(sentence_parts) > 1:
            return sentence_parts
        if " " in text:
            return [item for item in text.split(" ") if item]
        sub_parts = re.split(r"([，、,；;：:]+)", text)
        if len(sub_parts) > 1:
            return [part for part in _recombine_delimited(sub_parts) if part]
        return [
            text[index : index + self._force_chunk_chars]
            for index in range(0, len(text), self._force_chunk_chars)
        ]

    def _build_segment_id(self, title: str, index: int) -> str:
        normalized_title = (
            re.sub(r"[^\w\u4e00-\u9fff]+", "_", title).strip("_") or "segment"
        )
        return f"{normalized_title[:30]}_{index:04d}"

    def _renumber_segments(
        self,
        prefix: str,
        segments: List[DocumentSegment],
    ) -> List[DocumentSegment]:
        normalized_prefix = (
            re.sub(r"[^\w\u4e00-\u9fff]+", "_", prefix).strip("_") or "document"
        )
        renumbered = [
            DocumentSegment(
                segment_id=f"{normalized_prefix}_{index:04d}",
                text=segment.text,
                title=segment.title,
                source_label=segment.source_label,
                estimated_duration=segment.estimated_duration,
            )
            for index, segment in enumerate(segments, start=1)
        ]
        logger.info("Prepared {} segments from {}", len(renumbered), prefix)
        return renumbered