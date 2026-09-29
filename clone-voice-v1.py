#!/usr/bin/env python3
"""
TTS Voice Cloning Script v1
Supports multiple TTS frameworks via YAML profile configuration
"""

import argparse
import glob
import os
import re
import sys
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import xml.etree.ElementTree as ET

# Import modules from src directory
from src.tts_profile import TTSProfile
from src.ssml_parser import SSMLParser
from src.text_segmenter import TextSegmenter
from src.tts_factory import TTSFactory


def expand_text_files(pattern: str) -> List[Path]:
    """
    Expand wildcard pattern and return list of .txt files
    
    Args:
        pattern: File path pattern (can include wildcards like *.txt)
    
    Returns:
        List of Path objects for matching .txt files
    
    Raises:
        ValueError: If pattern doesn't end with .txt
    """
    # Validate that pattern ends with .txt
    if not pattern.lower().endswith('.txt'):
        raise ValueError("File pattern must end with .txt")
    
    # Check if pattern contains wildcards
    if '*' in pattern or '?' in pattern:
        # Use glob to expand pattern
        matched_files = glob.glob(pattern, recursive=False)
        
        # Filter to ensure all are .txt files and exist
        text_files = []
        for file_path in matched_files:
            path = Path(file_path)
            if path.exists() and path.suffix.lower() == '.txt':
                text_files.append(path)
        
        # Sort for consistent ordering
        text_files.sort()
        return text_files
    else:
        # Single file path
        path = Path(pattern)
        if path.exists() and path.suffix.lower() == '.txt':
            return [path]
        else:
            return []








def parse_arguments(profile: TTSProfile) -> argparse.Namespace:
    """Parse command line arguments based on profile configuration"""
    
    parser = argparse.ArgumentParser(
        description="TTS Voice Cloning Script v1",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage with default parameters
  python clone-voice-v1.py -m qwen3-tts-12hz-0.6b-base -t input.txt -o output.wav
  
  # With voice cloning
  python clone-voice-v1.py -m qwen3-tts-12hz-0.6b-base -t input.txt -o output.wav --voice-clone-audio reference.wav
  
  # With custom parameters
  python clone-voice-v1.py -m qwen3-tts-12hz-0.6b-base -t input.txt -o output.wav --temperature 0.8 --speed 1.2
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
    
    # Model-specific arguments (will be populated from profile)
    args, remaining = parser.parse_known_args()
    
    # Get model configuration
    model_config = profile.get_model_config(args.model)
    
    # Add model-specific parameters
    if 'parameters' in model_config:
        for param_name, param_config in model_config['parameters'].items():
            arg_name = param_name.replace('_', '-')
            
            # Determine argument type
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
        # Try to load profile for richer help output (with model-specific options)
        prelim_parser = argparse.ArgumentParser(add_help=False)
        prelim_parser.add_argument('-p', '--profile', default='tts-profiles.yaml', type=str)
        try:
            prelim_args, _ = prelim_parser.parse_known_args()
            if os.path.exists(prelim_args.profile):
                profile = TTSProfile(prelim_args.profile)
                parse_arguments(profile)  # Will print full help with model-specific args and exit
        except Exception:
            pass
        # Fallback: print basic help without profile dependency
        print("TTS Voice Cloning Script v1")
        print()
        print("Usage: python clone-voice-v1.py -m MODEL -t TEXT_FILE -o OUTPUT [options]")
        print()
        print("Required arguments:")
        print("  -m, --model MODEL    TTS model to use (choices depend on profile)")
        print("  -t, --text-file FILE Input text file path(s), supports wildcards (e.g., *.txt)")
        print("  -o, --output FILE    Output audio file path")
        print()
        print("Optional arguments:")
        print("  -p, --profile FILE   Path to TTS profile YAML file (default: tts-profiles.yaml)")
        print("  --hf-mirror URL      Hugging Face mirror URL for faster download in China")
        print("  --language LANG       Language for TTS synthesis (default: Chinese)")
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
    
    # Get model configuration
    model_config = profile.get_model_config(args.model)
    print(f"Using model: {model_config['name']}")
    print(f"Framework: {model_config['framework']}")
    print(f"Max tokens: {model_config['max_tokens']}")
    print(f"Supports SSML: {model_config['supports_ssml']}")
    
    # Check device availability
    import torch
    device = "CPU" if not torch.cuda.is_available() else "GPU"
    print(f"Device: {device}")
    if device == "CPU":
        print("Note: Running in CPU mode. Synthesis may be slower.")
    
    # Expand wildcard patterns and find text files
    text_files = expand_text_files(args.text_file)
    
    if not text_files:
        print(f"Error: No .txt files found matching pattern: {args.text_file}")
        sys.exit(1)
    
    print(f"\nFound {len(text_files)} text file(s) to process:")
    for i, file_path in enumerate(text_files, 1):
        print(f"  {i}. {file_path}")
    
    # Create TTS model (load once for all files)
    tts_model = TTSFactory.create_model(model_config, args)
    
    # Process each text file
    total_success = 0
    total_segments = 0
    
    for file_idx, text_file in enumerate(text_files, 1):
        print(f"\n{'=' * 60}")
        print(f"Processing file {file_idx}/{len(text_files)}: {text_file.name}")
        print(f"{'=' * 60}")
        
        # Read input text
        with open(text_file, 'r', encoding='utf-8') as f:
            text = f.read()
        
        print(f"Text length: {len(text)} characters")
        
        # Check if text is SSML
        ssml_parser = SSMLParser()
        is_ssml = ssml_parser.is_ssml(text)
        
        if is_ssml:
            print("Detected SSML format")
            
            # Extract plain text from SSML for segmentation
            plain_text = ssml_parser.extract_text_from_ssml(text)
            print(f"Extracted plain text length: {len(plain_text)} characters")
            
            # Validate SSML length (check if it's too long for single synthesis)
            is_valid, error_msg = ssml_parser.validate_ssml(text, model_config['max_tokens'])
            if not is_valid:
                print(f"Warning: {error_msg}")
                print("SSML text is too long, will segment and process in parts")
            
            # Segment the plain text
            segmenter = TextSegmenter()
            segments = segmenter.segment_text(plain_text, model_config['max_tokens'], use_cpu_mode=(device == "CPU"))
            print(f"Text segmented into {len(segments)} parts")
            texts_to_synthesize = segments
        else:
            print("Detected plain text format")
            
            # Segment text
            segmenter = TextSegmenter()
            segments = segmenter.segment_text(text, model_config['max_tokens'], use_cpu_mode=(device == "CPU"))
            
            print(f"Text segmented into {len(segments)} parts")
            texts_to_synthesize = segments
        
        # Determine output path for this file
        output_path = Path(args.output)
        if len(text_files) > 1:
            # Multiple files: use original filename with new extension
            file_output = output_path.parent / f"{text_file.stem}{output_path.suffix}"
        else:
            # Single file: use specified output path
            file_output = output_path
        
        # Synthesize each segment
        file_success = 0
        
        for i, text_segment in enumerate(texts_to_synthesize):
            if len(texts_to_synthesize) > 1:
                segment_output = file_output.parent / f"{file_output.stem}_part{i+1}{file_output.suffix}"
            else:
                segment_output = file_output
            
            print(f"\nSynthesizing segment {i+1}/{len(texts_to_synthesize)}...")
            print(f"Segment length: {len(text_segment)} characters")
            
            if tts_model.synthesize(text_segment, str(segment_output)):
                file_success += 1
            else:
                print(f"Failed to synthesize segment {i+1}")
        
        print(f"\nFile {text_file.name}: {file_success}/{len(texts_to_synthesize)} segments successful")
        total_success += file_success
        total_segments += len(texts_to_synthesize)
    
    # Final summary
    print(f"\n{'=' * 60}")
    print("Overall Summary")
    print(f"{'=' * 60}")
    print(f"Total files processed: {len(text_files)}")
    print(f"Total segments: {total_segments}")
    print(f"Successful segments: {total_success}")
    print(f"Failed segments: {total_segments - total_success}")
    
    if total_success == total_segments:
        print("\n✓ All segments synthesized successfully!")
        return 0
    else:
        print(f"\n✗ {total_segments - total_success} segment(s) failed to synthesize")
        return 1


if __name__ == '__main__':
    sys.exit(main())