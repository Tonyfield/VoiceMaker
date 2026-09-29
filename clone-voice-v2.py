#!/usr/bin/env python3
"""
TTS Voice Cloning Script v2
Supports JSON input with multiple segments and voice cloning
"""

import argparse
import json
import os
import sys
import yaml
from pathlib import Path
from typing import Dict, List, Optional

# Fix Unicode encoding issue on Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Import modules from src directory
from src.tts_profile import TTSProfile
from src.tts_factory import TTSFactory


def parse_arguments(profile: TTSProfile) -> argparse.Namespace:
    """Parse command line arguments based on profile configuration"""
    
    parser = argparse.ArgumentParser(
        description="TTS Voice Cloning Script v2 - JSON Input",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  python clone-voice-v2.py -i input.json -o output/阿房宫赋-%%02d.mp3
  
  # With custom parameters
  python clone-voice-v2.py -i input.json -o output/阿房宫赋-%%02d.mp3 --temperature 0.8 --speed 1.2
  
JSON Format:
  {
    "tts-model": "qwen3-tts-12hz-0.6b-base",
    "reference_audio": "../samples/voice-lyx-30s.mp3",
    "segments": [
      {
        "text": "六王毕，四海一，蜀山兀，阿房出。",
        "desc": "仅以标点符号断句"
      },
      {
        "text": "覆压三百余里，隔离天日。",
        "desc": "仅以标点符号断句，夹杂轻笑"
      }
    ]
  }

Output Pattern:
  Use %%02d for 2-digit zero-padded numbers (01, 02, 03...)
  Use %%03d for 3-digit zero-padded numbers (001, 002, 003...)
        """
    )
    
    # Required arguments
    parser.add_argument(
        '-i', '--input',
        required=True,
        type=str,
        help='Input JSON file path'
    )
    
    parser.add_argument(
        '-o', '--output',
        required=True,
        type=str,
        help='Output audio file path pattern. Use %%02d for segment numbering (e.g., output-%%02d.mp3)'
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
    
    # parser.add_argument(
    #     '--language',
    #     type=str,
    #     default='Chinese',
    #     help='Language for TTS synthesis (default: Chinese)'
    # )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without actually synthesizing'
    )
    
    # Parse initial arguments
    args, remaining = parser.parse_known_args()
    
    # Load JSON file to get model name
    try:
        with open(args.input, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
    except FileNotFoundError:
        print(f"Error: JSON input file not found: {args.input}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON format in {args.input}: {e}")
        sys.exit(1)
    
    # Validate JSON structure
    if 'tts-model' not in json_data:
        print("Error: JSON must contain 'tts-model' field")
        sys.exit(1)
    
    if 'segments' not in json_data:
        print("Error: JSON must contain 'segments' field")
        sys.exit(1)
    
    if not isinstance(json_data['segments'], list):
        print("Error: 'segments' must be a list")
        sys.exit(1)
    
    # Validate model name
    model_name = json_data['tts-model']
    available_models = profile.list_models()
    if model_name not in available_models:
        print(f"Error: Unknown model '{model_name}'")
        print(f"Available models: {', '.join(available_models)}")
        sys.exit(1)
    
    # Get model configuration
    model_config = profile.get_model_config(model_name)
    
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
    
    # Store JSON data in args for later use
    args.json_data = json_data
    
    return args


def validate_json_data(json_data: Dict) -> tuple[bool, str]:
    """
    Validate JSON input data structure
    
    Args:
        json_data: Parsed JSON data
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    # Check required fields
    required_fields = ['tts-model', 'segments']
    for field in required_fields:
        if field not in json_data:
            return False, f"Missing required field: {field}"
    
    # Validate segments
    segments = json_data['segments']
    if not isinstance(segments, list):
        return False, "'segments' must be a list"
    
    if len(segments) == 0:
        return False, "'segments' list cannot be empty"
    
    # Validate each segment
    for i, segment in enumerate(segments):
        if not isinstance(segment, dict):
            return False, f"Segment {i+1} must be a dictionary"
        
        if 'text' not in segment:
            return False, f"Segment {i+1} missing required field: 'text'"
        
        if not isinstance(segment['text'], str):
            return False, f"Segment {i+1} 'text' must be a string"
        
        if len(segment['text'].strip()) == 0:
            return False, f"Segment {i+1} 'text' cannot be empty"
    
    # Validate reference_audio if present
    if 'reference_audio' in json_data:
        ref_audio = json_data['reference_audio']
        if not isinstance(ref_audio, str):
            return False, "'reference_audio' must be a string"
        
        # Check if file exists
        ref_path = Path(ref_audio)
        if not ref_path.exists():
            return False, f"Reference audio file not found: {ref_audio}"
    
    return True, ""


def expand_output_pattern(pattern: str, segment_index: int) -> str:
    """
    Expand output pattern with segment index
    
    Args:
        pattern: Output pattern (e.g., "output-%%02d.mp3")
        segment_index: Segment index (1-based)
    
    Returns:
        Expanded output path
    """
    # Replace %02d, %03d, etc. with actual index
    # Note: In command line, %% is used to escape %
    pattern = pattern.replace('%%02d', f'{segment_index:02d}')
    pattern = pattern.replace('%%03d', f'{segment_index:03d}')
    pattern = pattern.replace('%%d', f'{segment_index}')
    
    return pattern


def main():
    """Main function"""
    
    # Load profile
    profile_path = 'tts-profiles.yaml'
    if not os.path.exists(profile_path):
        print(f"Error: Profile file not found: {profile_path}")
        sys.exit(1)
    
    profile = TTSProfile(profile_path)
    
    # Parse arguments
    args = parse_arguments(profile)
    
    # Validate JSON data
    is_valid, error_msg = validate_json_data(args.json_data)
    if not is_valid:
        print(f"Error: {error_msg}")
        sys.exit(1)
    
    # Get model configuration
    model_name = args.json_data['tts-model']
    model_config = profile.get_model_config(model_name)
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
    
    # Get reference audio if provided
    reference_audio = args.json_data.get('reference_audio', None)
    if reference_audio:
        print(f"Reference audio: {reference_audio}")
        # Add to args for model initialization
        args.voice_clone_audio = reference_audio
    
    # Get segments
    segments = args.json_data['segments']
    print(f"\nFound {len(segments)} segment(s) to process:")
    for i, segment in enumerate(segments, 1):
        text_preview = segment['text'][:50] + "..." if len(segment['text']) > 50 else segment['text']
        desc = segment.get('desc', 'No description')
        print(f"  {i}. {text_preview}")
        print(f"     Description: {desc}")
    
    # Check output pattern
    output_pattern = args.output
    if '%%' not in output_pattern:
        print(f"\nWarning: Output pattern '{output_pattern}' does not contain %%02d or %%03d")
        print("All segments will be written to the same file (only last segment will remain)")
        print("Consider using pattern like 'output-%%02d.mp3' to save each segment separately")
    
    # Create output directory if needed
    output_path = Path(output_pattern)
    output_dir = output_path.parent
    if output_dir and not output_dir.exists():
        print(f"\nCreating output directory: {output_dir}")
        output_dir.mkdir(parents=True, exist_ok=True)
    
    # Dry run mode
    if args.dry_run:
        print("\n" + "=" * 60)
        print("DRY RUN MODE - No actual synthesis will be performed")
        print("=" * 60)
        for i, segment in enumerate(segments, 1):
            output_file = expand_output_pattern(output_pattern, i)
            print(f"\nSegment {i}:")
            print(f"  Text: {segment['text'][:100]}...")
            print(f"  Output: {output_file}")
            print(f"  Description: {segment.get('desc', 'No description')}")
        print("\nDry run complete. Use without --dry-run to perform actual synthesis.")
        return 0
    
    # Create TTS model
    print(f"\nLoading TTS model...")
    tts_model = TTSFactory.create_model(model_config, args)
    
    # Synthesize each segment
    total_success = 0
    total_segments = len(segments)
    
    print("\n" + "=" * 60)
    print("Starting synthesis")
    print("=" * 60)
    
    for i, segment in enumerate(segments, 1):
        text = segment['text']
        desc = segment.get('desc', 'No description')
        
        # Generate output filename
        output_file = expand_output_pattern(output_pattern, i)
        
        print(f"\nSegment {i}/{total_segments}")
        print(f"Description: {desc}")
        print(f"Text length: {len(text)} characters")
        print(f"Output: {output_file}")
        
        # Synthesize
        if tts_model.synthesize(text, output_file):
            print(f"✓ Successfully synthesized to {output_file}")
            total_success += 1
        else:
            print(f"✗ Failed to synthesize segment {i}")
    
    # Final summary
    print(f"\n{'=' * 60}")
    print("Overall Summary")
    print(f"{'=' * 60}")
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