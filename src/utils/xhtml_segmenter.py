"""
XHTML text segmentation module for processing book content.
Extracts and segments text from XHTML files while avoiding duplicates and annotations.
"""
import os
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup, NavigableString
from loguru import logger


class XHTMLSegmenter:
    """
    Segments XHTML book content into manageable chunks for TTS processing.
    
    Features:
    - Parses XHTML files from book/OEBPS/Text directory
    - Removes duplicate content (title in head and h1 in body)
    - Filters out annotations like [3]
    - Segments text into chunks of ~500 bytes (±200)
    - Preserves sentence boundaries
    - Generates segment IDs with document and sequence numbers
    - Records processing metadata
    - Exports results to JSON
    """
    
    def __init__(
        self,
        book_dir: str,
        target_chunk_size: int = 500,
        chunk_variance: int = 200,
        min_chunk_size: int = 200
    ):
        """
        Initialize the XHTML segmenter.
        
        Args:
            book_dir: Path to the book directory containing OEBPS/Text
            target_chunk_size: Target size of each chunk in bytes (default: 500)
            chunk_variance: Allowed variance from target size (default: 200)
            min_chunk_size: Minimum size for the last chunk before merging (default: 200)
        """
        self.book_dir = Path(book_dir)
        self.text_dir = self.book_dir / "OEBPS" / "Text"
        self.target_chunk_size = target_chunk_size
        self.chunk_variance = chunk_variance
        self.min_chunk_size = min_chunk_size
        self.segments = []
        
        if not self.text_dir.exists():
            raise FileNotFoundError(f"Text directory not found: {self.text_dir}")
    
    def process_all_files(self) -> List[Dict]:
        """
        Process all XHTML files in the Text directory.
        
        Returns:
            List of all segments with metadata
        """
        xhtml_files = sorted(self.text_dir.glob("*.xhtml"))
        logger.debug(f"Found {len(xhtml_files)} XHTML files to process")
        
        for file_path in xhtml_files:
            try:
                self.process_file(file_path)
            except Exception as e:
                logger.error(f"Error processing {file_path}: {e}")
        
        return self.segments
    
    def process_file(self, file_path: Path) -> List[Dict]:
        """
        Process a single XHTML file and extract segments.
        
        Args:
            file_path: Path to the XHTML file
            
        Returns:
            List of segments from this file
        """
        logger.debug(f"Processing {file_path.name}")
        
        # Extract document number from filename
        doc_match = re.match(r"part(\d+)\.xhtml", file_path.name)
        doc_num = doc_match.group(1) if doc_match else "000"
        doc_id = f"{int(doc_num):03d}" if doc_match else "000"
        
        # Parse the XHTML file
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        soup = BeautifulSoup(content, 'html.parser')
        
        # Extract title from head
        title_tag = soup.find('title')
        title = title_tag.get_text().strip() if title_tag else ""
        
        # Find the main h1 tag (usually the chapter title)
        h1_tag = soup.find('h1')
        h1_text = h1_tag.get_text().strip() if h1_tag else ""
        
        # Skip if title and h1 are the same (duplicate)
        if title == h1_text:
            logger.debug(f"Skipping duplicate title in {file_path.name}")
            title = ""  # Clear title to avoid duplication
        
        # Extract all text content
        text_content = self._extract_text_content(soup)
        
        # If we have a title/h1 that's not in the body, prepend it
        if h1_text and h1_text not in text_content:
            text_content = h1_text + "\n\n" + text_content
        
        # Segment the text
        segments = self._segment_text(text_content, doc_id, title, file_path.name)
        
        # Add to global segments list
        self.segments.extend(segments)
        
        return segments
    
    def _extract_text_content(self, soup: BeautifulSoup) -> str:
        """
        Extract clean text content from the parsed XHTML.
        
        Removes:
        - Script and style elements
        - Annotations like [3]
        - Image references
        
        Args:
            soup: Parsed BeautifulSoup object
            
        Returns:
            Cleaned text content
        """
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.extract()
        
        # Get all text
        text = soup.get_text()
        
        # Remove annotations like [3], [4], etc.
        text = re.sub(r'\[\d+\]', '', text)
        
        # Clean up whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = ' '.join(chunk for chunk in chunks if chunk)
        
        return text
    
    def _segment_text(
        self,
        text: str,
        doc_id: str,
        title: str,
        source_file: str
    ) -> List[Dict]:
        """
        Segment text into chunks of appropriate size.
        
        Args:
            text: Text to segment
            doc_id: Document ID (e.g., "001")
            title: Document title
            source_file: Source filename
            
        Returns:
            List of segment dictionaries
        """
        segments = []
        
        # Split into sentences
        sentences = re.split(r'([。！？.!?])', text)
        sentences = [s1 + s2 for s1, s2 in zip(sentences[::2], sentences[1::2] + [""])]
        sentences = [s.strip() for s in sentences if s.strip()]
        
        # Create segments
        current_segment = ""
        segment_num = 1
        
        for sentence in sentences:
            # Check if adding this sentence would exceed the target size
            if len(current_segment.encode('utf-8')) >= self.target_chunk_size - self.chunk_variance:
                if current_segment:
                    # Save the current segment
                    segment_id = f"{doc_id}_{self._clean_title(title)}_{segment_num:03d}"
                    segments.append(self._create_segment(
                        segment_id, current_segment, doc_id, title, source_file
                    ))
                    current_segment = sentence
                    segment_num += 1
                else:
                    # Sentence itself is too long, add it anyway
                    segment_id = f"{doc_id}_{self._clean_title(title)}_{segment_num:03d}"
                    segments.append(self._create_segment(
                        segment_id, sentence, doc_id, title, source_file
                    ))
                    segment_num += 1
            else:
                current_segment += sentence
        
        # Handle the last segment
        if current_segment:
            # If the last segment is too small, merge with previous
            if (len(current_segment.encode('utf-8')) < self.min_chunk_size and 
                segments and 
                len(segments[-1]['content'].encode('utf-8')) + len(current_segment.encode('utf-8')) < self.target_chunk_size + self.chunk_variance):
                
                # Merge with previous segment
                segments[-1]['content'] += current_segment
                segments[-1]['size_bytes'] = len(segments[-1]['content'].encode('utf-8'))
                segments[-1]['processed_at'] = datetime.now().isoformat()
            else:
                # Add as a new segment
                segment_id = f"{doc_id}_{self._clean_title(title)}_{segment_num:03d}"
                segments.append(self._create_segment(
                    segment_id, current_segment, doc_id, title, source_file
                ))
        
        return segments
    
    def _clean_title(self, title: str) -> str:
        """
        Clean title for use in segment ID.
        
        Args:
            title: Original title
            
        Returns:
            Cleaned title safe for filenames
        """
        # Remove special characters and replace with underscores
        cleaned = re.sub(r'[^\w\u4e00-\u9fff]', '_', title)
        # Limit length
        return cleaned[:20] if cleaned else "untitled"
    
    def _create_segment(
        self,
        segment_id: str,
        content: str,
        doc_id: str,
        title: str,
        source_file: str
    ) -> Dict:
        """
        Create a segment dictionary with metadata.
        
        Args:
            segment_id: Unique segment identifier
            content: Text content of the segment
            doc_id: Document ID
            title: Document title
            source_file: Source filename
            
        Returns:
            Segment dictionary
        """
        return {
            "segment_id": segment_id,
            "doc_id": doc_id,
            "title": title,
            "source_file": source_file,
            "content": content,
            "size_bytes": len(content.encode('utf-8')),
            "processed_at": datetime.now().isoformat()
        }
    
    def save_to_json(self, output_path: str) -> None:
        """
        Save all segments to a JSON file.
        
        Args:
            output_path: Path to save the JSON file
        """
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output, 'w', encoding='utf-8') as f:
            json.dump(self.segments, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Saved {len(self.segments)} segments to {output}")
    
    def get_segments(self) -> List[Dict]:
        """
        Get all processed segments.
        
        Returns:
            List of segment dictionaries
        """
        return self.segments
    
    def get_segments_by_doc(self, doc_id: str) -> List[Dict]:
        """
        Get all segments for a specific document.
        
        Args:
            doc_id: Document ID (e.g., "001")
            
        Returns:
            List of segments for the document
        """
        return [s for s in self.segments if s['doc_id'] == doc_id]