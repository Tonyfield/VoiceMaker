"""Voice profile management for stored profiles and reusable reference assets."""

import hashlib
import json
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from src.config import config
from src.exceptions import VoiceProfileError, VoiceProfileNotFoundError


class VoiceProfile:
    """
    Voice profile for storing voice characteristics.
    
    Stores metadata about a voice profile including:
    - Reference audio path
    - Creation date
    - Language
    - Description
    """
    
    def __init__(
        self,
        name: str,
        reference_audio: str,
        language: str = "auto",
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Initialize a voice profile.
        
        Args:
            name: Profile name
            reference_audio: Path to reference audio file
            language: Language code for the voice
            description: Optional description
            metadata: Additional metadata
        """
        self.name = name
        self.reference_audio = reference_audio
        self.language = language
        self.description = description
        self.metadata = metadata or {}
        self.created_at = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert profile to dictionary."""
        return {
            "name": self.name,
            "reference_audio": self.reference_audio,
            "language": self.language,
            "description": self.description,
            "metadata": self.metadata,
            "created_at": self.created_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VoiceProfile":
        """
        Create profile from dictionary.
        
        Args:
            data: Dictionary containing profile data
            
        Returns:
            VoiceProfile instance
        """
        profile = cls(
            name=data["name"],
            reference_audio=data["reference_audio"],
            language=data.get("language", "auto"),
            description=data.get("description", ""),
            metadata=data.get("metadata", {})
        )
        profile.created_at = data.get("created_at", profile.created_at)
        return profile


class VoiceProfileManager:
    """
    Manager for voice profiles.
    
    Handles saving, loading, and listing voice profiles.
    """
    
    def __init__(self, storage_dir: Optional[Path] = None) -> None:
        """
        Initialize the profile manager.
        
        Args:
            storage_dir: Directory to store profiles (uses config if not provided)
        """
        self.storage_dir = storage_dir or config.voice_profiles_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.asset_dir = self.storage_dir / "_assets"
        self.asset_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Voice profile manager initialized: {self.storage_dir}")

    def _get_asset_metadata_path(self, file_hash: str) -> Path:
        return self.asset_dir / f"{file_hash}.json"

    def _find_asset_file(self, file_hash: str) -> Optional[Path]:
        for path in sorted(self.asset_dir.glob(f"{file_hash}.*")):
            if path.suffix.lower() != ".json" and path.is_file():
                return path
        return None

    def asset_exists(self, file_hash: str) -> bool:
        return self._find_asset_file(file_hash) is not None

    def get_asset_path(self, file_hash: str) -> Path:
        asset_path = self._find_asset_file(file_hash)
        if asset_path is None:
            raise VoiceProfileNotFoundError(
                f"Voice asset not found: {file_hash}",
                {"file_hash": file_hash},
            )
        return asset_path

    def get_asset_info(self, file_hash: str) -> Dict[str, Any]:
        asset_path = self.get_asset_path(file_hash)
        metadata_path = self._get_asset_metadata_path(file_hash)
        metadata: Dict[str, Any] = {}
        if metadata_path.exists():
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                metadata = {}

        content_type = metadata.get("content_type") or mimetypes.guess_type(asset_path.name)[0] or "application/octet-stream"
        return {
            "file_hash": file_hash,
            "original_name": metadata.get("original_name") or asset_path.name,
            "content_type": content_type,
            "size": metadata.get("size") or asset_path.stat().st_size,
            "suffix": asset_path.suffix.lower(),
            "created_at": metadata.get("created_at") or datetime.now().isoformat(),
            "audio_url": f"/api/voice-assets/{file_hash}/audio",
        }

    def store_asset_bytes(
        self,
        data: bytes,
        original_name: str,
        expected_hash: Optional[str] = None,
        content_type: str = "",
    ) -> Dict[str, Any]:
        file_hash = hashlib.sha256(data).hexdigest()
        if expected_hash and expected_hash.lower() != file_hash:
            raise VoiceProfileError(
                "Reference audio hash mismatch",
                {"expected_hash": expected_hash, "actual_hash": file_hash},
            )

        if self.asset_exists(file_hash):
            return self.get_asset_info(file_hash)

        suffix = Path(original_name).suffix.lower() or ".bin"
        asset_path = self.asset_dir / f"{file_hash}{suffix}"
        asset_path.write_bytes(data)

        metadata_path = self._get_asset_metadata_path(file_hash)
        metadata = {
            "file_hash": file_hash,
            "original_name": original_name,
            "content_type": content_type,
            "size": len(data),
            "created_at": datetime.now().isoformat(),
        }
        metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
        return self.get_asset_info(file_hash)
    
    def _get_profile_path(self, name: str) -> Path:
        """
        Get the file path for a profile.
        
        Args:
            name: Profile name
            
        Returns:
            Path to the profile file
        """
        return self.storage_dir / f"{name}.json"
    
    def save(self, profile: VoiceProfile) -> Path:
        """
        Save a voice profile.
        
        Args:
            profile: Voice profile to save
            
        Returns:
            Path to the saved profile file
            
        Raises:
            VoiceProfileError: If saving fails
        """
        try:
            profile_path = self._get_profile_path(profile.name)
            
            with open(profile_path, "w", encoding="utf-8") as f:
                json.dump(profile.to_dict(), f, indent=2, ensure_ascii=False)
            
            logger.success(f"Voice profile saved: {profile.name}")
            return profile_path
            
        except Exception as e:
            raise VoiceProfileError(
                f"Failed to save voice profile: {e}",
                {"profile_name": profile.name}
            )
    
    def load(self, name: str) -> VoiceProfile:
        """
        Load a voice profile.
        
        Args:
            name: Profile name to load
            
        Returns:
            Loaded voice profile
            
        Raises:
            VoiceProfileNotFoundError: If profile not found
            VoiceProfileError: If loading fails
        """
        profile_path = self._get_profile_path(name)
        
        if not profile_path.exists():
            raise VoiceProfileNotFoundError(
                f"Voice profile not found: {name}",
                {"profile_name": name}
            )
        
        try:
            with open(profile_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            profile = VoiceProfile.from_dict(data)
            logger.info(f"Voice profile loaded: {name}")
            return profile
            
        except json.JSONDecodeError as e:
            raise VoiceProfileError(
                f"Invalid profile file format: {e}",
                {"profile_name": name}
            )
        except Exception as e:
            raise VoiceProfileError(
                f"Failed to load voice profile: {e}",
                {"profile_name": name}
            )
    
    def delete(self, name: str) -> bool:
        """
        Delete a voice profile.
        
        Args:
            name: Profile name to delete
            
        Returns:
            True if deleted successfully
            
        Raises:
            VoiceProfileNotFoundError: If profile not found
        """
        profile_path = self._get_profile_path(name)
        
        if not profile_path.exists():
            raise VoiceProfileNotFoundError(
                f"Voice profile not found: {name}",
                {"profile_name": name}
            )
        
        profile_path.unlink()
        logger.info(f"Voice profile deleted: {name}")
        return True
    
    def list_profiles(self) -> List[str]:
        """
        List all saved voice profiles.
        
        Returns:
            List of profile names
        """
        profiles = list(self.storage_dir.glob("*.json"))
        return sorted([p.stem for p in profiles])
    
    def exists(self, name: str) -> bool:
        """
        Check if a profile exists.
        
        Args:
            name: Profile name to check
            
        Returns:
            True if profile exists
        """
        return self._get_profile_path(name).exists()
    
    def create_profile(
        self,
        name: str,
        reference_audio: str,
        language: str = "auto",
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> VoiceProfile:
        """
        Create and save a new voice profile.
        
        Args:
            name: Profile name
            reference_audio: Path to reference audio
            language: Language code
            description: Profile description
            
        Returns:
            Created voice profile
        """
        profile = VoiceProfile(
            name=name,
            reference_audio=reference_audio,
            language=language,
            description=description,
            metadata=metadata,
        )
        self.save(profile)
        return profile
