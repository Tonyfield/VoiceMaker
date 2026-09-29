"""
Logging configuration for TTS Voice Cloning application.
Uses loguru for structured logging with file rotation.
"""
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger


def setup_logger(
    log_dir: str = "log",
    app_name: str = "tts-vc",
    level: str = "INFO",
    console_level: Optional[str] = None,
    file_level: Optional[str] = None,
    retention: str = "30 days",
    max_size: str = "50 MB"
) -> None:
    """
    Configure loguru logger with file and console handlers.
    
    Log files are stored in: log/yyyy-mm-dd/<app-name>-yyyy-mm-dd-HH-MM-SS.log
    
    Args:
        log_dir: Base directory for log files.
        app_name: Application name for log file prefix.
        level: Fallback log level when console_level/file_level not specified.
        console_level: Log level for stdout (overrides level).
        file_level: Log level for file (overrides level).
        retention: How long to keep log files.
        max_size: Maximum total disk usage for logs.
    """
    # Remove default handler
    logger.remove()
    
    # Create log directory structure
    today = datetime.now().strftime("%Y-%m-%d")
    log_path = Path(log_dir) / today
    log_path.mkdir(parents=True, exist_ok=True)
    
    # Log file name with timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    log_file = log_path / f"{app_name}-{timestamp}.log"
    
    # Common format for both handlers
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )
    
    # File format (no color, includes module/line info)
    file_format = (
        "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
        "{level: <8} | "
        "{name}:{function}:{line: <4} | "
        "{message}"
    )
    
    # Console handler (colored, default INFO)
    logger.add(
        sys.stdout,
        format=log_format,
        level=console_level or level or "INFO",
        colorize=True
    )
    
    # File handler (no color, default DEBUG)
    logger.add(
        str(log_file),
        format=file_format,
        level=file_level or level or "DEBUG",
        rotation=max_size,
        retention=retention,
        compression="zip"
    )


def get_logger():
    """
    Return the configured logger instance.
    
    Returns:
        The loguru logger instance.
    """
    return logger
