"""
Main entry point for TTS Voice Cloning application.

This module provides the primary entry point for running the TTS Voice Cloning
application, initializing configuration, logging, and launching the CLI.
"""
import sys

from loguru import logger

from src.cli import main as cli_main
from src.config import config


def main() -> int:
    """
    Main entry point for the TTS Voice Cloning application.
    
    Initializes configuration and logging, then runs the CLI interface.
    
    Returns:
        Exit code (0 for success, non-zero for errors).
    """
    # Load configuration
    config.load()
    
    # Setup logging
    log_level = config.log_level
    logger.add(
        config.log_dir / "tts-vc.log",
        rotation=config.log_max_size,
        retention=config.log_retention,
        level=log_level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"
    )
    
    logger.info("Starting TTS Voice Cloning application")
    
    # Run CLI
    try:
        cli_main()
        return 0
    except Exception as e:
        logger.exception("Application error")
        return 1


if __name__ == "__main__":
    sys.exit(main())
