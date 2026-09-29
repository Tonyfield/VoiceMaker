"""Document loading and segmentation utilities for long-form TTS tasks."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from bs4 import BeautifulSoup
from ebooklib import ITEM_DOCUMENT, epub
from loguru import logger

from src.model_profiles import ModelServiceProfile, get_token_estimator
from src.exceptions import TextProcessingError
from src.utils.text import clean_text


@dataclass
class DocumentSegment:
    """Normalized text segment ready for synthesis."""

    segment_id: str
    text: str
    title: str
    source_label: str
    estimated_duration: float

    def to_dict(self) -> dict:
        """Convert the segment to a JSON-serializable dictionary."""
        return asdict(self)


class DocumentIngestService:
    """Load supported document types and split them into TTS-sized chunks."""

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
        model_profile: ModelServiceProfile | None = None,
    ) -> None:
        self.model_profile = model_profile
        if model_profile is not None:
            self.max_chars_per_segment = min(
                max_chars_per_segment,
                model_profile.segmentation.max_chars_per_segment,
            )
            self.max_estimated_duration_seconds = min(
                max_estimated_duration_seconds,
                model_profile.segmentation.max_estimated_duration_seconds,
            )
            self.max_tokens_per_segment = model_profile.effective_token_limit
            self._force_chunk_chars = int(model_profile.segmentation.force_chunk_chars)
            self._token_estimator = get_token_estimator(
                model_profile.segmentation.strategy_id
            )
        else:
            self.max_chars_per_segment = max_chars_per_segment
            self.max_estimated_duration_seconds = max_estimated_duration_seconds
            self.max_tokens_per_segment = None
            self._force_chunk_chars = max(40, self.max_chars_per_segment // 2)
            self._token_estimator = lambda text: len(text)

    @classmethod
    def supports(cls, file_path: Path) -> bool:
        """Return whether the file type is supported."""
        return file_path.suffix.lower() in cls.SUPPORTED_SUFFIXES

    def load_segments(self, file_path: Path) -> List[DocumentSegment]:
        """Load a document and return normalized TTS segments."""
        if not self.supports(file_path):
            raise TextProcessingError(
                f"Unsupported document type: {file_path.suffix}",
                {"supported": sorted(self.SUPPORTED_SUFFIXES)},
            )

        suffix = file_path.suffix.lower()
        if suffix in {".txt", ".md", ".markdown"}:
            text = self._load_text_document(file_path)
            title = file_path.stem
            return self._split_document_text(text, title=title, source_label=file_path.name)

        if suffix == ".pdf":
            return self._load_pdf_segments(file_path)

        if suffix == ".docx":
            return self._load_docx_segments(file_path)

        if suffix == ".epub":
            return self._load_epub_segments(file_path)

        if suffix in {".html", ".htm", ".xhtml"}:
            html_text = self._html_to_text(file_path.read_text(encoding="utf-8", errors="ignore"))
            return self._split_document_text(
                html_text,
                title=file_path.stem,
                source_label=file_path.name,
            )

        raise TextProcessingError(f"No loader available for {file_path.suffix}")

    def _load_text_document(self, file_path: Path) -> str:
        raw_text = file_path.read_text(encoding="utf-8", errors="ignore")
        if file_path.suffix.lower() in {".md", ".markdown"}:
            return self._strip_markdown(raw_text)
        return raw_text

    def _load_pdf_segments(self, file_path: Path) -> List[DocumentSegment]:
        try:
            import fitz
        except ImportError as exc:
            raise TextProcessingError("PyMuPDF is required for PDF support") from exc

        segments: List[DocumentSegment] = []
        with fitz.open(file_path) as document:
            for page_number, page in enumerate(document, start=1):
                text = clean_text(page.get_text("text"))
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
            raise TextProcessingError("python-docx is required for DOCX support") from exc

        document = Document(file_path)
        paragraphs = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
        return self._split_document_text(
            "\n\n".join(paragraphs),
            title=file_path.stem,
            source_label=file_path.name,
        )

    def _load_epub_segments(self, file_path: Path) -> List[DocumentSegment]:
        book = epub.read_epub(str(file_path))
        segments: List[DocumentSegment] = []

        for item in book.get_items_of_type(ITEM_DOCUMENT):
            content = item.get_content().decode("utf-8", errors="ignore")
            text = self._html_to_text(content)
            if not text:
                continue
            title = self._extract_html_title(content) or Path(item.file_name).stem
            segments.extend(
                self._split_document_text(
                    text,
                    title=title,
                    source_label=item.file_name,
                )
            )

        return self._renumber_segments(file_path.stem, segments)

    def _extract_html_title(self, html: str) -> Optional[str]:
        soup = BeautifulSoup(html, "html.parser")
        heading = soup.find(["h1", "h2", "title"])
        if heading and heading.get_text(strip=True):
            return heading.get_text(strip=True)
        return None

    def _html_to_text(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        return clean_text(soup.get_text(" "))

    def _strip_markdown(self, markdown_text: str) -> str:
        text = re.sub(r"```.*?```", " ", markdown_text, flags=re.DOTALL)
        text = re.sub(r"`([^`]*)`", r"\1", text)
        text = re.sub(r"!\[[^\]]*\]\([^\)]*\)", " ", text)
        text = re.sub(r"\[([^\]]+)\]\([^\)]*\)", r"\1", text)
        text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"[*_~>#-]", " ", text)
        return clean_text(text)

    def _split_document_text(
        self,
        text: str,
        title: str,
        source_label: str,
    ) -> List[DocumentSegment]:
        cleaned = clean_text(text)
        if not cleaned:
            return []

        sentences = self._split_sentences(cleaned)
        chunks: List[str] = []
        current = ""

        for sentence in sentences:
            sentence = clean_text(sentence)
            if not sentence:
                continue
            candidate = f"{current} {sentence}".strip() if current else sentence
            if current and self._would_exceed_limits(candidate):
                chunks.append(current)
                current = sentence
                continue
            if not current and self._would_exceed_limits(candidate):
                chunks.extend(self._force_split(sentence))
                current = ""
                continue
            current = candidate

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

    def _split_sentences(self, text: str) -> List[str]:
        parts = re.split(r"(?<=[。！？!?\.])\s*", text)
        if len(parts) == 1:
            return [text]
        return [part.strip() for part in parts if part.strip()]

    def _would_exceed_limits(self, text: str) -> bool:
        token_limit_exceeded = False
        if self.max_tokens_per_segment is not None:
            token_limit_exceeded = self._token_estimator(text) > self.max_tokens_per_segment

        return (
            len(text) > self.max_chars_per_segment
            or self._estimate_duration(text) > self.max_estimated_duration_seconds
            or token_limit_exceeded
        )

    def _estimate_duration(self, text: str) -> float:
        chinese_chars = sum(1 for character in text if "\u4e00" <= character <= "\u9fff")
        latin_words = len(re.findall(r"[A-Za-z0-9']+", text))

        if chinese_chars and chinese_chars >= max(1, latin_words * 2):
            return chinese_chars / 4.0
        if latin_words:
            return (latin_words / 150) * 60
        return max(len(text) / 12.0, 1.0)

    def _force_split(self, text: str) -> List[str]:
        words = self._chunkable_units(text)
        chunks: List[str] = []
        current = ""

        for unit in words:
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
        if " " in text:
            return [item for item in text.split(" ") if item]
        return [
            text[index:index + self._force_chunk_chars]
            for index in range(0, len(text), self._force_chunk_chars)
        ]

    def _build_segment_id(self, title: str, index: int) -> str:
        normalized_title = re.sub(r"[^\w\u4e00-\u9fff]+", "_", title).strip("_") or "segment"
        return f"{normalized_title[:30]}_{index:04d}"

    def _renumber_segments(self, prefix: str, segments: List[DocumentSegment]) -> List[DocumentSegment]:
        normalized_prefix = re.sub(r"[^\w\u4e00-\u9fff]+", "_", prefix).strip("_") or "document"
        renumbered: List[DocumentSegment] = []
        for index, segment in enumerate(segments, start=1):
            renumbered.append(
                DocumentSegment(
                    segment_id=f"{normalized_prefix}_{index:04d}",
                    text=segment.text,
                    title=segment.title,
                    source_label=segment.source_label,
                    estimated_duration=segment.estimated_duration,
                )
            )
        logger.info("Prepared {} segments from {}", len(renumbered), prefix)
        return renumbered