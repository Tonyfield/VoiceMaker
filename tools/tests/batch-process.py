#!/usr/bin/env python3
"""
Batch processing script for clone-voice-v2.py
Processes multiple JSON files in a directory
"""

import argparse
import glob
import os
import subprocess
import sys
from pathlib import Path
from typing import List


def find_json_files(directory: str, pattern: str = "*.json") -> List[Path]:
    """
    Find all JSON files in directory matching pattern
    
    Args:
        directory: Directory to search
        pattern: File pattern (default: *.json)
    
    Returns:
        List of Path objects for matching JSON files
    """
    search_path = Path(directory) / pattern
    json_files = list(Path(directory).glob(pattern))
    
    # Sort for consistent ordering
    json_files.sort()
    
    return json_files


def generate_output_pattern(json_file: Path, output_dir: Path, pattern: str = "%%02d") -> str:
    """
    Generate output pattern for a JSON file
    
    Args:
        json_file: Input JSON file path
        output_dir: Output directory
        pattern: Number pattern (default: %%02d)
    
    Returns:
        Output file pattern
    """
    # Use JSON filename without extension
    base_name = json_file.stem
    output_pattern = output_dir / f"{base_name}-{pattern}.mp3"
    return str(output_pattern)


def run_clone_voice_v2(json_file: Path, output_pattern: str, dry_run: bool = False,
                       extra_args: List[str] = None) -> bool:
    """
    Run clone-voice-v2.py for a single JSON file
    
    Args:
        json_file: Input JSON file
        output_pattern: Output file pattern
        dry_run: If True, only show commands without executing
        extra_args: Additional arguments to pass to clone-voice-v2.py
    
    Returns:
        True if successful, False otherwise
    """
    # Build command
    cmd = ["python", "clone-voice-v2.py", "-i", str(json_file), "-o", output_pattern]
    
    if dry_run:
        cmd.append("--dry-run")
    
    if extra_args:
        cmd.extend(extra_args)
    
    # Print command
    print(f"\n{'=' * 60}")
    print(f"Processing: {json_file.name}")
    print(f"Command: {' '.join(cmd)}")
    print(f"{'=' * 60}")
    
    if dry_run:
        return True
    
    # Run command
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error processing {json_file.name}")
        print(f"Return code: {e.returncode}")
        print(f"STDOUT: {e.stdout}")
        print(f"STDERR: {e.stderr}")
        return False


def main():
    """Main function"""
    
    parser = argparse.ArgumentParser(
        description="Batch processing script for clone-voice-v2.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process all JSON files in current directory
  python batch-process.py -d . -o output
  
  # Process specific pattern
  python batch-process.py -d input -o output -p "chapter-*.json"
  
  # Dry run to preview
  python batch-process.py -d . -o output --dry-run
  
  # With additional arguments
  python batch-process.py -d . -o output -- --temperature 0.8 --speed 1.2
        """
    )
    
    parser.add_argument(
        '-d', '--directory',
        default='.',
        type=str,
        help='Directory containing JSON files (default: current directory)'
    )
    
    parser.add_argument(
        '-o', '--output',
        default='output',
        type=str,
        help='Output directory (default: output)'
    )
    
    parser.add_argument(
        '-p', '--pattern',
        default='*.json',
        type=str,
        help='File pattern to match (default: *.json)'
    )
    
    parser.add_argument(
        '--number-pattern',
        default='%%02d',
        type=str,
        help='Number pattern for output files (default: %%02d)'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show commands without executing'
    )
    
    parser.add_argument(
        '--continue-on-error',
        action='store_true',
        help='Continue processing even if some files fail'
    )
    
    parser.add_argument(
        'extra_args',
        nargs=argparse.REMAINDER,
        help='Additional arguments to pass to clone-voice-v2.py (use -- to separate)'
    )
    
    args = parser.parse_args()
    
    # Validate directory
    input_dir = Path(args.directory)
    if not input_dir.exists():
        print(f"Error: Directory not found: {input_dir}")
        sys.exit(1)
    
    # Find JSON files
    json_files = find_json_files(str(input_dir), args.pattern)
    
    if not json_files:
        print(f"No JSON files found matching pattern '{args.pattern}' in {input_dir}")
        sys.exit(1)
    
    print(f"Found {len(json_files)} JSON file(s) to process:")
    for i, json_file in enumerate(json_files, 1):
        print(f"  {i}. {json_file.name}")
    
    # Create output directory
    output_dir = Path(args.output)
    if not output_dir.exists():
        print(f"\nCreating output directory: {output_dir}")
        output_dir.mkdir(parents=True, exist_ok=True)
    
    # Process each JSON file
    total_files = len(json_files)
    success_count = 0
    failure_count = 0
    
    for i, json_file in enumerate(json_files, 1):
        # Generate output pattern
        output_pattern = generate_output_pattern(json_file, output_dir, args.number_pattern)
        
        # Run clone-voice-v2.py
        success = run_clone_voice_v2(
            json_file,
            output_pattern,
            dry_run=args.dry_run,
            extra_args=args.extra_args
        )
        
        if success:
            success_count += 1
            print(f"✓ Successfully processed {json_file.name} ({i}/{total_files})")
        else:
            failure_count += 1
            print(f"✗ Failed to process {json_file.name} ({i}/{total_files})")
            
            if not args.continue_on_error:
                print("\nStopping due to error. Use --continue-on-error to continue processing.")
                break
    
    # Final summary
    print(f"\n{'=' * 60}")
    print("Batch Processing Summary")
    print(f"{'=' * 60}")
    print(f"Total files: {total_files}")
    print(f"Successful: {success_count}")
    print(f"Failed: {failure_count}")
    
    if failure_count == 0:
        print("\n✓ All files processed successfully!")
        return 0
    else:
        print(f"\n✗ {failure_count} file(s) failed to process")
        return 1


if __name__ == '__main__':
    sys.exit(main())