"""
Multi-channel model download manager with HuggingFace mirrors and ModelScope support.

This module provides a robust download system that handles network errors through
rotation retry strategies across multiple sources including HuggingFace mirrors
and ModelScope.
"""
import os
import time
import hashlib
import tempfile
import shutil
from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from loguru import logger
from urllib.parse import urlparse

from src.exceptions import ModelDownloadError


class DownloadSource(Enum):
    """Enumeration of available download sources."""
    HUGGINGFACE = "huggingface"
    MODELSCOPE = "modelscope"


@dataclass
class DownloadResult:
    """Result of a download operation."""
    success: bool
    local_path: Optional[Path] = None
    source: Optional[DownloadSource] = None
    error: Optional[str] = None
    attempts: int = 0
    total_time: float = 0.0


@dataclass
class MirrorConfig:
    """Configuration for a mirror site."""
    name: str
    base_url: str
    priority: int = 0  # Lower is higher priority
    is_available: bool = True
    last_failure_time: Optional[float] = None
    failure_count: int = 0


class BaseDownloader(ABC):
    """Abstract base class for download channels."""
    
    def __init__(self, cache_dir: Path):
        """
        Initialize the downloader.
        
        Args:
            cache_dir: Directory to store downloaded models.
        """
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    @abstractmethod
    def download(
        self,
        model_id: str,
        target_path: Optional[Path] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> DownloadResult:
        """
        Download a model from the source.
        
        Args:
            model_id: Model identifier (e.g., "tts_models/multilingual/multi-dataset/xtts_v2")
            target_path: Optional target path for the download
            progress_callback: Optional callback for progress updates
            
        Returns:
            DownloadResult with download status and path
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if the download source is available."""
        pass
    
    @property
    @abstractmethod
    def source_type(self) -> DownloadSource:
        """Return the source type."""
        pass


class HuggingFaceDownloader(BaseDownloader):
    """
    HuggingFace downloader with mirror support and rotation retry.
    
    Supports multiple HuggingFace mirrors for regions with restricted access.
    Implements rotation retry strategy to handle network failures.
    """
    
    # Default HuggingFace mirrors (ordered by priority)
    DEFAULT_MIRRORS = [
        MirrorConfig("hf-mirror.com", "https://hf-mirror.com", priority=0),
        MirrorConfig("huggingface.co", "https://huggingface.co", priority=1),
        MirrorConfig("hf.co", "https://hf.co", priority=2),
    ]
    
    # Additional mirrors for China region
    CHINA_MIRRORS = [
        MirrorConfig("hf-mirror.com", "https://hf-mirror.com", priority=0),
        MirrorConfig("modelscope", "https://modelscope.cn/models", priority=1, is_available=False),
    ]
    
    def __init__(
        self,
        cache_dir: Path,
        mirrors: Optional[List[MirrorConfig]] = None,
        max_retries: int = 3,
        retry_delay: float = 2.0,
        timeout: float = 300.0
    ):
        """
        Initialize HuggingFace downloader.
        
        Args:
            cache_dir: Directory to store downloaded models.
            mirrors: List of mirror configurations (uses defaults if not provided).
            max_retries: Maximum number of retries per mirror.
            retry_delay: Base delay between retries (exponential backoff).
            timeout: Download timeout in seconds.
        """
        super().__init__(cache_dir)
        self.mirrors = mirrors or self.DEFAULT_MIRRORS.copy()
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.timeout = timeout
        self._current_mirror_index = 0
    
    @property
    def source_type(self) -> DownloadSource:
        return DownloadSource.HUGGINGFACE
    
    def _get_sorted_mirrors(self) -> List[MirrorConfig]:
        """Get mirrors sorted by priority and availability."""
        available = [m for m in self.mirrors if m.is_available]
        return sorted(available, key=lambda m: (m.priority, m.failure_count))
    
    def _mark_mirror_failure(self, mirror: MirrorConfig) -> None:
        """Mark a mirror as failed and update its status."""
        mirror.failure_count += 1
        mirror.last_failure_time = time.time()
        
        # Temporarily disable mirror after too many failures
        if mirror.failure_count >= self.max_retries:
            mirror.is_available = False
            logger.warning(f"Mirror {mirror.name} temporarily disabled due to failures")
    
    def _reset_mirror_status(self) -> None:
        """Reset mirror status for a new download session."""
        for mirror in self.mirrors:
            # Re-enable mirrors that were disabled
            if not mirror.is_available and mirror.last_failure_time:
                # Re-enable after 5 minutes
                if time.time() - mirror.last_failure_time > 300:
                    mirror.is_available = True
                    mirror.failure_count = 0
                    logger.info(f"Mirror {mirror.name} re-enabled")
    
    def is_available(self) -> bool:
        """Check if any mirror is available."""
        return any(m.is_available for m in self.mirrors)
    
    def download(
        self,
        model_id: str,
        target_path: Optional[Path] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> DownloadResult:
        """
        Download a model from HuggingFace with mirror rotation.
        
        Args:
            model_id: HuggingFace model ID (e.g., "coqui/XTTS-v2")
            target_path: Optional target path for the download
            progress_callback: Optional callback for progress updates
            
        Returns:
            DownloadResult with download status and path
        """
        start_time = time.time()
        attempts = 0
        last_error = None
        
        self._reset_mirror_status()
        
        # Determine target path
        if target_path is None:
            target_path = self.cache_dir / model_id.replace("/", "_")
        
        # Check if already cached
        if target_path.exists() and self._validate_cache(target_path, model_id):
            logger.info(f"Model already cached at: {target_path}")
            return DownloadResult(
                success=True,
                local_path=target_path,
                source=self.source_type,
                attempts=0,
                total_time=time.time() - start_time
            )
        
        # Try each mirror with retries
        for mirror in self._get_sorted_mirrors():
            if not mirror.is_available:
                continue
            
            for retry in range(self.max_retries):
                attempts += 1
                try:
                    logger.info(f"Attempting download from {mirror.name} (attempt {retry + 1})")
                    
                    result = self._download_from_mirror(
                        model_id=model_id,
                        mirror=mirror,
                        target_path=target_path,
                        progress_callback=progress_callback
                    )
                    
                    if result.success:
                        return result
                    
                except Exception as e:
                    last_error = str(e)
                    logger.warning(f"Download failed from {mirror.name}: {e}")
                    
                    # Exponential backoff
                    if retry < self.max_retries - 1:
                        delay = self.retry_delay * (2 ** retry)
                        logger.info(f"Retrying in {delay}s...")
                        time.sleep(delay)
            
            # Mark mirror as failed after all retries exhausted
            self._mark_mirror_failure(mirror)
        
        # All mirrors failed
        return DownloadResult(
            success=False,
            error=last_error or "All mirrors failed",
            attempts=attempts,
            total_time=time.time() - start_time
        )
    
    def _download_from_mirror(
        self,
        model_id: str,
        mirror: MirrorConfig,
        target_path: Path,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> DownloadResult:
        """
        Download from a specific mirror.
        
        Args:
            model_id: Model ID to download
            mirror: Mirror configuration
            target_path: Target path for download
            progress_callback: Progress callback function
            
        Returns:
            DownloadResult with status
        """
        start_time = time.time()
        
        try:
            # Set environment variable for HuggingFace mirror
            original_endpoint = os.environ.get("HF_ENDPOINT", "")
            os.environ["HF_ENDPOINT"] = mirror.base_url
            
            logger.info(f"Using HuggingFace endpoint: {mirror.base_url}")
            
            # Use huggingface_hub for download
            from huggingface_hub import snapshot_download, login
            
            # Download to temporary directory first
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir) / model_id.replace("/", "_")
                
                local_path = snapshot_download(
                    repo_id=model_id,
                    local_dir=str(temp_path),
                    local_dir_use_symlinks=False,
                    etag_timeout=self.timeout,
                    headers={"User-Agent": f"TTS-Voice-Cloning/1.0"}
                )
                
                # Move to final location
                if target_path.exists():
                    shutil.rmtree(target_path)
                
                shutil.move(str(temp_path), str(target_path))
            
            # Restore original endpoint
            if original_endpoint:
                os.environ["HF_ENDPOINT"] = original_endpoint
            elif "HF_ENDPOINT" in os.environ:
                del os.environ["HF_ENDPOINT"]
            
            logger.success(f"Model downloaded successfully from {mirror.name}")
            
            return DownloadResult(
                success=True,
                local_path=target_path,
                source=self.source_type,
                attempts=1,
                total_time=time.time() - start_time
            )
            
        except ImportError as e:
            raise ModelDownloadError(
                f"huggingface_hub not installed: {e}",
                {"solution": "pip install huggingface_hub"}
            )
        except Exception as e:
            # Restore environment on failure
            if "original_endpoint" in dir() and original_endpoint:
                os.environ["HF_ENDPOINT"] = original_endpoint
            raise
    
    def _validate_cache(self, cache_path: Path, model_id: str) -> bool:
        """
        Validate that cached model is complete and valid.
        
        Args:
            cache_path: Path to cached model
            model_id: Model ID for validation
            
        Returns:
            True if cache is valid
        """
        # Check for essential files
        essential_files = ["config.json"]
        for filename in essential_files:
            if not (cache_path / filename).exists():
                logger.debug(f"Cache missing essential file: {filename}")
                return False
        
        return True


class ModelScopeDownloader(BaseDownloader):
    """
    ModelScope downloader for models available on ModelScope platform.
    
    ModelScope is an alternative model repository popular in China region.
    """
    
    # Mapping of HuggingFace model IDs to ModelScope IDs
    MODEL_MAPPING = {
        "coqui/XTTS-v2": "AI-ModelScope/XTTS-v2",
        "tts_models/multilingual/multi-dataset/xtts_v2": "AI-ModelScope/XTTS-v2",
        "SWivid/F5-TTS_Emilia-ZH-EN": "SWivid/F5-TTS_Emilia-ZH-EN",
    }
    
    def __init__(
        self,
        cache_dir: Path,
        timeout: float = 300.0,
        max_retries: int = 3
    ):
        """
        Initialize ModelScope downloader.
        
        Args:
            cache_dir: Directory to store downloaded models.
            timeout: Download timeout in seconds.
            max_retries: Maximum number of retries.
        """
        super().__init__(cache_dir)
        self.timeout = timeout
        self.max_retries = max_retries
    
    @property
    def source_type(self) -> DownloadSource:
        return DownloadSource.MODELSCOPE
    
    def is_available(self) -> bool:
        """Check if ModelScope SDK is available."""
        try:
            import modelscope
            return True
        except ImportError:
            return False
    
    def _get_modelscope_id(self, hf_model_id: str) -> Optional[str]:
        """
        Get ModelScope model ID from HuggingFace ID.
        
        Args:
            hf_model_id: HuggingFace model ID
            
        Returns:
            ModelScope model ID or None if not available
        """
        return self.MODEL_MAPPING.get(hf_model_id)
    
    def download(
        self,
        model_id: str,
        target_path: Optional[Path] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> DownloadResult:
        """
        Download a model from ModelScope.
        
        Args:
            model_id: Model identifier (HuggingFace format, will be mapped to ModelScope)
            target_path: Optional target path for the download
            progress_callback: Optional callback for progress updates
            local_files_only: If True, only use local files without downloading
            
        Returns:
            DownloadResult with download status and path
        """
        start_time = time.time()
        
        # Get ModelScope model ID
        ms_model_id = self._get_modelscope_id(model_id)
        if not ms_model_id:
            return DownloadResult(
                success=False,
                error=f"Model {model_id} not available on ModelScope",
                attempts=0,
                total_time=time.time() - start_time
            )
        
        # Determine target path
        if target_path is None:
            target_path = self.cache_dir / model_id.replace("/", "_")
        
        # Check if already cached
        if target_path.exists():
            logger.info(f"Model already cached at: {target_path}")
            return DownloadResult(
                success=True,
                local_path=target_path,
                source=self.source_type,
                attempts=0,
                total_time=time.time() - start_time
            )
        
        try:
            from modelscope import snapshot_download
            
            logger.info(f"Downloading from ModelScope: {ms_model_id}")
            
            # Use local_dir to specify download location and local_files_only to avoid re-download
            result = snapshot_download(
                ms_model_id,
                cache_dir=str(self.cache_dir),
                local_dir=str(target_path),
                local_files_only=False  # Set to True to only use local files
            )
            
            # Verify the model was downloaded/cached
            if Path(result).exists():
                logger.success(f"Model downloaded from ModelScope: {result}")
                return DownloadResult(
                    success=True,
                    local_path=Path(result),
                    source=self.source_type,
                    attempts=1,
                    total_time=time.time() - start_time
                )
            else:
                return DownloadResult(
                    success=False,
                    error=f"Model download failed, path not found: {result}",
                    attempts=1,
                    total_time=time.time() - start_time
                )
            
        except ImportError as e:
            return DownloadResult(
                success=False,
                error=f"ModelScope SDK not installed: {e}",
                attempts=0,
                total_time=time.time() - start_time
            )
        except Exception as e:
            return DownloadResult(
                success=False,
                error=f"ModelScope download failed: {e}",
                attempts=1,
                total_time=time.time() - start_time
            )


class MultiChannelDownloader:
    """
    Multi-channel model download manager.
    
    Coordinates downloads across multiple sources (HuggingFace mirrors, ModelScope)
    with automatic failover and retry strategies.
    """
    
    def __init__(
        self,
        cache_dir: Path,
        prefer_modelscope: bool = False,
        max_retries: int = 3
    ):
        """
        Initialize multi-channel downloader.
        
        Args:
            cache_dir: Directory to store downloaded models.
            prefer_modelscope: Whether to prefer ModelScope over HuggingFace.
            max_retries: Maximum retries per channel.
        """
        self.cache_dir = cache_dir
        self.prefer_modelscope = prefer_modelscope
        self.max_retries = max_retries
        
        # Initialize download channels
        self._hf_downloader = HuggingFaceDownloader(
            cache_dir=cache_dir,
            max_retries=max_retries
        )
        self._ms_downloader = ModelScopeDownloader(
            cache_dir=cache_dir,
            max_retries=max_retries
        )
        
        # Channel priority (lower is higher priority)
        self._channels = self._init_channels()
    
    def _init_channels(self) -> List[BaseDownloader]:
        """Initialize download channels in priority order."""
        channels = []
        
        if self.prefer_modelscope and self._ms_downloader.is_available():
            channels.append(self._ms_downloader)
        
        if self._hf_downloader.is_available():
            channels.append(self._hf_downloader)
        
        if not self.prefer_modelscope and self._ms_downloader.is_available():
            channels.append(self._ms_downloader)
        
        return channels
    
    def download(
        self,
        model_id: str,
        target_path: Optional[Path] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> Path:
        """
        Download a model using multi-channel strategy.
        
        Args:
            model_id: Model identifier
            target_path: Optional target path for the download
            progress_callback: Optional callback for progress updates
            
        Returns:
            Path to the downloaded model
            
        Raises:
            ModelDownloadError: If all download channels fail
        """
        logger.info(f"Starting multi-channel download for: {model_id}")
        
        # Determine target path
        if target_path is None:
            target_path = self.cache_dir / model_id.replace("/", "_")
        
        # Check cache first
        if target_path.exists():
            logger.info(f"Model already cached at: {target_path}")
            return target_path
        
        # Try each channel
        errors = []
        for channel in self._channels:
            if not channel.is_available():
                continue
            
            logger.info(f"Trying download channel: {channel.source_type.value}")
            
            result = channel.download(
                model_id=model_id,
                target_path=target_path,
                progress_callback=progress_callback
            )
            
            if result.success:
                logger.success(
                    f"Download successful from {result.source.value} "
                    f"after {result.attempts} attempts in {result.total_time:.1f}s"
                )
                return result.local_path
            
            errors.append(f"{channel.source_type.value}: {result.error}")
            logger.warning(f"Channel {channel.source_type.value} failed: {result.error}")
        
        # All channels failed
        error_msg = f"All download channels failed for {model_id}:\n" + "\n".join(errors)
        raise ModelDownloadError(
            error_msg,
            {
                "model_id": model_id,
                "channels_tried": [c.source_type.value for c in self._channels],
                "errors": errors
            }
        )
    
    def get_cache_info(self, model_id: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a cached model.
        
        Args:
            model_id: Model identifier
            
        Returns:
            Dictionary with cache info or None if not cached
        """
        cache_path = self.cache_dir / model_id.replace("/", "_")
        
        if not cache_path.exists():
            return None
        
        # Get directory size
        total_size = sum(
            f.stat().st_size for f in cache_path.rglob("*") if f.is_file()
        )
        
        return {
            "path": str(cache_path),
            "size_mb": total_size / (1024 * 1024),
            "exists": True
        }
    
    def clear_cache(self, model_id: Optional[str] = None) -> int:
        """
        Clear model cache.
        
        Args:
            model_id: Specific model to clear, or None for all
            
        Returns:
            Number of models cleared
        """
        if model_id:
            cache_path = self.cache_dir / model_id.replace("/", "_")
            if cache_path.exists():
                shutil.rmtree(cache_path)
                return 1
            return 0
        
        # Clear all
        count = 0
        for item in self.cache_dir.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
                count += 1
        return count


# Convenience function for direct use
def download_model(
    model_id: str,
    cache_dir: Optional[Path] = None,
    prefer_modelscope: bool = False
) -> Path:
    """
    Download a model using multi-channel strategy.
    
    Args:
        model_id: Model identifier (e.g., "coqui/XTTS-v2")
        cache_dir: Cache directory (uses default if not provided)
        prefer_modelscope: Whether to prefer ModelScope over HuggingFace
        
    Returns:
        Path to the downloaded model
        
    Raises:
        ModelDownloadError: If download fails
    """
    if cache_dir is None:
        cache_dir = Path("./models")
    
    downloader = MultiChannelDownloader(
        cache_dir=cache_dir,
        prefer_modelscope=prefer_modelscope
    )
    
    return downloader.download(model_id)