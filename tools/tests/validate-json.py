#!/usr/bin/env python3
"""
JSON validation script for clone-voice-v2.py
Validates JSON input files before processing
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple


def validate_json_structure(json_data: Dict) -> Tuple[bool, List[str]]:
    """
    Validate JSON structure for clone-voice-v2.py
    
    Args:
        json_data: Parsed JSON data
    
    Returns:
        Tuple of (is_valid, error_messages)
    """
    errors = []
    
    # Check required fields
    required_fields = ['tts-model', 'segments']
    for field in required_fields:
        if field not in json_data:
            errors.append(f"Missing required field: '{field}'")
    
    # Validate tts-model
    if 'tts-model' in json_data:
        model_name = json_data['tts-model']
        if not isinstance(model_name, str):
            errors.append(f"'tts-model' must be a string, got {type(model_name).__name__}")
        elif len(model_name.strip()) == 0:
            errors.append(f"'tts-model' cannot be empty")
    
    # Validate reference_audio if present
    if 'reference_audio' in json_data:
        ref_audio = json_data['reference_audio']
        if not isinstance(ref_audio, str):
            errors.append(f"'reference_audio' must be a string, got {type(ref_audio).__name__}")
        else:
            # Check if file exists
            ref_path = Path(ref_audio)
            if not ref_path.exists():
                errors.append(f"Reference audio file not found: {ref_audio}")
    
    # Validate segments
    if 'segments' in json_data:
        segments = json_data['segments']
        if not isinstance(segments, list):
            errors.append(f"'segments' must be a list, got {type(segments).__name__}")
        elif len(segments) == 0:
            errors.append(f"'segments' list cannot be empty")
        else:
            # Validate each segment
            for i, segment in enumerate(segments, 1):
                segment_errors = validate_segment(segment, i)
                errors.extend(segment_errors)
    
    return (len(errors) == 0, errors)


def validate_segment(segment: Dict, index: int) -> List[str]:
    """
    Validate a single segment
    
    Args:
        segment: Segment data
        index: Segment index (1-based)
    
    Returns:
        List of error messages
    """
    errors = []
    prefix = f"Segment {index}:"
    
    # Check if segment is a dictionary
    if not isinstance(segment, dict):
        errors.append(f"{prefix} Must be a dictionary, got {type(segment).__name__}")
        return errors
    
    # Check required field: text
    if 'text' not in segment:
        errors.append(f"{prefix} Missing required field: 'text'")
    else:
        text = segment['text']
        if not isinstance(text, str):
            errors.append(f"{prefix} 'text' must be a string, got {type(text).__name__}")
        elif len(text.strip()) == 0:
            errors.append(f"{prefix} 'text' cannot be empty")
    
    # Check optional field: desc
    if 'desc' in segment:
        desc = segment['desc']
        if not isinstance(desc, str):
            errors.append(f"{prefix} 'desc' must be a string, got {type(desc).__name__}")
    
    return errors


def validate_json_file(json_file: Path, profile_path: str = 'tts-profiles.yaml') -> Tuple[bool, List[str]]:
    """
    Validate a JSON file
    
    Args:
        json_file: Path to JSON file
        profile_path: Path to TTS profile YAML file
    
    Returns:
        Tuple of (is_valid, error_messages)
    """
    errors = []
    
    # Check if file exists
    if not json_file.exists():
        errors.append(f"File not found: {json_file}")
        return (False, errors)
    
    # Check file extension
    if json_file.suffix.lower() != '.json':
        errors.append(f"File must have .json extension: {json_file}")
    
    # Try to parse JSON
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
    except json.JSONDecodeError as e:
        errors.append(f"Invalid JSON format: {e}")
        return (False, errors)
    except Exception as e:
        errors.append(f"Error reading file: {e}")
        return (False, errors)
    
    # Validate structure
    is_valid, structure_errors = validate_json_structure(json_data)
    errors.extend(structure_errors)
    
    # Validate model name against profile
    if is_valid and 'tts-model' in json_data:
        try:
            from src.tts_profile import TTSProfile
            profile = TTSProfile(profile_path)
            model_name = json_data['tts-model']
            available_models = profile.list_models()
            
            if model_name not in available_models:
                errors.append(f"Unknown model '{model_name}'")
                errors.append(f"Available models: {', '.join(available_models)}")
        except Exception as e:
            errors.append(f"Warning: Could not validate model name: {e}")
    
    return (len(errors) == 0, errors)


def print_validation_result(json_file: Path, is_valid: bool, errors: List[str], verbose: bool = False):
    """
    Print validation result
    
    Args:
        json_file: JSON file path
        is_valid: Whether validation passed
        errors: List of error messages
        verbose: Whether to show detailed information
    """
    if is_valid:
        print(f"✓ {json_file.name}: VALID")
        if verbose:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                print(f"  Model: {data.get('tts-model', 'N/A')}")
                print(f"  Segments: {len(data.get('segments', []))}")
            print()
    else:
        print(f"✗ {json_file.name}: INVALID")
        for error in errors:
            print(f"  - {error}")
        print()


def main():
    """Main function"""
    
    parser = argparse.ArgumentParser(
        description="JSON validation script for clone-voice-v2.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Validate a single JSON file
  python validate-json.py input.json
  
  # Validate multiple JSON files
  python validate-json.py file1.json file2.json file3.json
  
  # Validate all JSON files in directory
  python validate-json.py -d .
  
  # Validate with verbose output
  python validate-json.py -v input.json
  
  # Use custom profile file
  python validate-json.py -p custom-profiles.yaml input.json
        """
    )
    
    parser.add_argument(
        'files',
        nargs='*',
        type=str,
        help='JSON files to validate'
    )
    
    parser.add_argument(
        '-d', '--directory',
        type=str,
        help='Directory containing JSON files to validate'
    )
    
    parser.add_argument(
        '-p', '--pattern',
        default='*.json',
        type=str,
        help='File pattern when using -d (default: *.json)'
    )
    
    parser.add_argument(
        '--profile',
        default='tts-profiles.yaml',
        type=str,
        help='Path to TTS profile YAML file (default: tts-profiles.yaml)'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Show detailed validation information'
    )
    
    parser.add_argument(
        '--strict',
        action='store_true',
        help='Exit with error code if any file is invalid'
    )
    
    args = parser.parse_args()
    
    # Collect files to validate
    json_files = []
    
    if args.directory:
        # Validate all JSON files in directory
        import glob
        pattern = Path(args.directory) / args.pattern
        json_files = list(Path(args.directory).glob(args.pattern))
        json_files.sort()
    elif args.files:
        # Validate specified files
        for file_path in args.files:
            json_files.append(Path(file_path))
    else:
        print("Error: No files specified. Use -d to specify a directory or provide file paths.")
        parser.print_help()
        sys.exit(1)
    
    if not json_files:
        print("No JSON files found to validate.")
        sys.exit(0)
    
    print(f"Validating {len(json_files)} JSON file(s)...\n")
    
    # Validate each file
    total_valid = 0
    total_invalid = 0
    
    for json_file in json_files:
        is_valid, errors = validate_json_file(json_file, args.profile)
        print_validation_result(json_file, is_valid, errors, args.verbose)
        
        if is_valid:
            total_valid += 1
        else:
            total_invalid += 1
    
    # Summary
    print(f"{'=' * 60}")
    print("Validation Summary")
    print(f"{'=' * 60}")
    print(f"Total files: {len(json_files)}")
    print(f"Valid: {total_valid}")
    print(f"Invalid: {total_invalid}")
    
    if total_invalid > 0:
        print(f"\n✗ {total_invalid} file(s) failed validation")
        if args.strict:
            return 1
    else:
        print("\n✓ All files are valid!")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())