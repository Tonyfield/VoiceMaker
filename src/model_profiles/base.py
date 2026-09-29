"""Shared model profile objects for remote model-service metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SegmentationSettings:
    """Operational text segmentation constraints for a model service."""

    strategy_id: str
    max_chars_per_segment: int
    max_estimated_duration_seconds: float
    max_input_tokens: int | None = None
    target_input_tokens: int | None = None
    force_chunk_chars: int = 80
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "max_chars_per_segment": self.max_chars_per_segment,
            "max_estimated_duration_seconds": self.max_estimated_duration_seconds,
            "max_input_tokens": self.max_input_tokens,
            "target_input_tokens": self.target_input_tokens,
            "force_chunk_chars": self.force_chunk_chars,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SegmentationSettings":
        return cls(
            strategy_id=str(payload.get("strategy_id") or "generic"),
            max_chars_per_segment=int(payload.get("max_chars_per_segment") or 280),
            max_estimated_duration_seconds=float(
                payload.get("max_estimated_duration_seconds") or 30.0
            ),
            max_input_tokens=(
                int(payload["max_input_tokens"])
                if payload.get("max_input_tokens") not in (None, "")
                else None
            ),
            target_input_tokens=(
                int(payload["target_input_tokens"])
                if payload.get("target_input_tokens") not in (None, "")
                else None
            ),
            force_chunk_chars=int(payload.get("force_chunk_chars") or 80),
            notes=str(payload.get("notes") or ""),
        )


@dataclass(frozen=True)
class ModelServiceProfile:
    """Remote model-service capabilities and text segmentation hints."""

    canonical_name: str
    label: str
    version: str
    requires_reference: bool
    supports_voice_instruction: bool
    supported_languages: list[str]
    min_reference_audio_seconds: float
    segmentation: SegmentationSettings
    task_inputs: list[dict[str, Any]] = field(default_factory=list)
    capabilities: dict[str, Any] = field(default_factory=dict)
    runtime: dict[str, Any] = field(default_factory=dict)
    service: dict[str, Any] = field(default_factory=dict)

    @property
    def effective_token_limit(self) -> int | None:
        return self.segmentation.target_input_tokens or self.segmentation.max_input_tokens

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_name": self.canonical_name,
            "label": self.label,
            "version": self.version,
            "requires_reference": self.requires_reference,
            "supports_voice_instruction": self.supports_voice_instruction,
            "supported_languages": list(self.supported_languages),
            "min_reference_audio_seconds": self.min_reference_audio_seconds,
            "segmentation": self.segmentation.to_dict(),
            "task_inputs": [dict(item) for item in self.task_inputs],
            "capabilities": dict(self.capabilities),
            "runtime": dict(self.runtime),
            "service": dict(self.service),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ModelServiceProfile":
        return cls(
            canonical_name=str(payload.get("canonical_name") or ""),
            label=str(payload.get("label") or payload.get("canonical_name") or ""),
            version=str(payload.get("version") or "unknown"),
            requires_reference=bool(payload.get("requires_reference", False)),
            supports_voice_instruction=bool(payload.get("supports_voice_instruction", False)),
            supported_languages=[str(item) for item in payload.get("supported_languages", [])],
            min_reference_audio_seconds=float(payload.get("min_reference_audio_seconds") or 0.0),
            segmentation=SegmentationSettings.from_dict(payload.get("segmentation") or {}),
            task_inputs=[
                dict(item)
                for item in payload.get("task_inputs", [])
                if isinstance(item, dict)
            ],
            capabilities=dict(payload.get("capabilities") or {}),
            runtime=dict(payload.get("runtime") or {}),
            service=dict(payload.get("service") or {}),
        )