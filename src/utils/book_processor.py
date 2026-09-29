"""
Command-line interface for processing XHTML books and converting to audio.
Combines XHTMLSegmenter and TTSConverter for end-to-end processing.
"""
import argparse
import json
import sys
from pathlib import Path

from loguru import logger

from src.utils.xhtml_segmenter import XHTMLSegmenter
from src.utils.tts_converter import TTSConverter
from src.models.xtts import XTTSModel


def setup_logging(verbose: bool = False) -> None:
    """Setup logging configuration."""
    logger.remove()
    level = "DEBUG" if verbose else "INFO"
    logger.add(sys.stderr, level=level)


def segment_command(args) -> None:
    """Handle the segment command."""
    logger.info(f"Segmenting XHTML files from {args.book_dir}")
    
    # Create segmenter
    segmenter = XHTMLSegmenter(
        book_dir=args.book_dir,
        target_chunk_size=args.chunk_size,
        chunk_variance=args.variance,
        min_chunk_size=args.min_size
    )
    
    # Process files
    segments = segmenter.process_all_files()
    
    # Save results
    segmenter.save_to_json(args.output)
    
    # Print summary
    logger.info(f"Created {len(segments)} segments from {len(set(s['doc_id'] for s in segments))} documents")
    
    # Show sample segments
    if args.verbose:
        logger.debug("Sample segments:")
        for segment in segments[:3]:
            logger.debug(f"  {segment['segment_id']}: {segment['content'][:50]}...")


def convert_command(args) -> None:
    """Handle the convert command."""
    logger.info(f"Converting segments from {args.segments} to audio")
    
    # Create TTS model
    model = XTTSModel()
    model.load_model()
    
    # Create converter
    converter = TTSConverter(
        model=model,
        output_dir=args.output_dir,
        reference_audio=args.reference,
        language=args.language
    )
    
    # Process segments
    if args.book_dir:
        # Process entire book
        audio_files = converter.process_book(
            book_dir=args.book_dir,
            segment_file=args.segments,
            resume=args.resume,
            skip_existing=args.skip_existing
        )
    else:
        # Process from segment file
        audio_files = converter.process_segment_file(
            segment_file=args.segments,
            resume=args.resume,
            skip_existing=args.skip_existing
        )
    
    # Print summary
    logger.info(f"Generated {len(audio_files)} audio files in {args.output_dir}")
    
    # Show progress
    progress = converter.get_progress()
    logger.info(f"Progress: {progress}")


def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description="Process XHTML books and convert to audio",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Segment a book into JSON
  python -m src.utils.book_processor segment book/ -o segments.json
  
  # Convert segments to audio
  python -m src.utils.book_processor convert segments.json -o audio/
  
  # Process entire book end-to-end
  python -m src.utils.book_processor convert --book-dir book/ -o audio/ --segments segments.json
        """
    )
    
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Segment command
    segment_parser = subparsers.add_parser(
        "segment",
        help="Segment XHTML files into JSON"
    )
    segment_parser.add_argument(
        "book_dir",
        help="Path to book directory containing OEBPS/Text"
    )
    segment_parser.add_argument(
        "-o", "--output",
        default="segments.json",
        help="Output JSON file path (default: segments.json)"
    )
    segment_parser.add_argument(
        "--chunk-size",
        type=int,
        default=500,
        help="Target chunk size in bytes (default: 500)"
    )
    segment_parser.add_argument(
        "--variance",
        type=int,
        default=200,
        help="Allowed variance from target size (default: 200)"
    )
    segment_parser.add_argument(
        "--min-size",
        type=int,
        default=200,
        help="Minimum size for last chunk before merging (default: 200)"
    )
    
    # Convert command
    convert_parser = subparsers.add_parser(
        "convert",
        help="Convert segments to audio"
    )
    convert_parser.add_argument(
        "segments",
        nargs="?",
        help="Path to segments JSON file"
    )
    convert_parser.add_argument(
        "--book-dir",
        help="Path to book directory (alternative to segments file)"
    )
    convert_parser.add_argument(
        "-o", "--output-dir",
        default="audio_output",
        help="Output directory for audio files (default: audio_output)"
    )
    convert_parser.add_argument(
        "-r", "--reference",
        help="Path to reference audio for voice cloning"
    )
    convert_parser.add_argument(
        "-l", "--language",
        default="zh-cn",
        help="Language code (default: zh-cn)"
    )
    convert_parser.add_argument(
        "--resume",
        action="store_true",
        default=True,
        help="Resume from existing files (default: True)"
    )
    convert_parser.add_argument(
        "--no-resume",
        dest="resume",
        action="store_false",
        help="Don't resume from existing files"
    )
    convert_parser.add_argument(
        "--skip-existing",
        action="store_true",
        default=True,
        help="Skip already converted segments (default: True)"
    )
    convert_parser.add_argument(
        "--no-skip-existing",
        dest="skip_existing",
        action="store_false",
        help="Don't skip already converted segments"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.verbose)
    
    # Handle commands
    if args.command == "segment":
        segment_command(args)
    elif args.command == "convert":
        if not args.segments and not args.book_dir:
            logger.error("Either segments file or book directory must be provided")
            sys.exit(1)
        convert_command(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()