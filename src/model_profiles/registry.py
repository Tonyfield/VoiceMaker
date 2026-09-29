"""YAML-driven model profile registry.

Loads model-profiles.yaml (single source of truth), applies ``_extends_``
inheritance, validates required fields, and exposes the same public API as
the previous per-model Python builders:

- build_model_service_profile(model_name, metadata)
- get_token_estimator(strategy_id)
"""

from __future__ import annotations

import math
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

import yaml

from src.model_profiles.base import ModelServiceProfile, SegmentationSettings

PROFILES_FILE = Path(__file__).resolve().parent.parent.parent / "model-profiles.yaml"

# ---------------------------------------------------------------------------
# YAML loading with defaults merge and _extends_ inheritance
# ---------------------------------------------------------------------------

_CACHE: dict[str, Any] | None = None

REQUIRED_TOP_KEYS = ("label", "adapter", "version", "capabilities", "segmentation", "runtime", "service")
REQUIRED_CAPABILITY_KEYS = ("requires_reference", "voice_instruction", "languages")
REQUIRED_SEGMENTATION_KEYS = ("estimator", "max_chars_per_segment", "max_estimated_duration_seconds")


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def load_profiles(force_reload: bool = False) -> dict[str, dict[str, Any]]:
    """Load and validate all model profiles from model-profiles.yaml."""
    global _CACHE
    if _CACHE is not None and not force_reload:
        return _CACHE

    if not PROFILES_FILE.exists():
        raise FileNotFoundError(f"Model profiles file not found: {PROFILES_FILE}")

    raw = yaml.safe_load(PROFILES_FILE.read_text(encoding="utf-8")) or {}
    defaults = raw.get("defaults") or {}
    profiles_raw = raw.get("profiles") or {}
    if not isinstance(profiles_raw, dict) or not profiles_raw:
        raise ValueError("model-profiles.yaml must contain a non-empty 'profiles' mapping")

    profiles: dict[str, dict[str, Any]] = {}
    for name, spec in profiles_raw.items():
        if not isinstance(spec, dict):
            raise ValueError(f"profile '{name}' must be a mapping")

        parent_name = spec.pop("_extends_", None)
        if parent_name is not None:
            parent = profiles.get(parent_name)
            if parent is None:
                raise ValueError(f"profile '{name}' extends unknown/unresolved profile '{parent_name}'")
            spec = _deep_merge(parent, spec)

        # Apply top-level defaults (capabilities / segmentation / service)
        for section in ("capabilities", "segmentation", "service"):
            section_defaults = defaults.get(section) or {}
            if section_defaults:
                spec[section] = _deep_merge(section_defaults, spec.get(section) or {})

        _validate_profile(name, spec)
        profiles[name] = spec

    _CACHE = profiles
    return profiles


def _validate_profile(name: str, spec: dict[str, Any]) -> None:
    for key in REQUIRED_TOP_KEYS:
        if key not in spec:
            raise ValueError(f"profile '{name}' is missing required key: {key}")
    for key in REQUIRED_CAPABILITY_KEYS:
        if key not in spec["capabilities"]:
            raise ValueError(f"profile '{name}'.capabilities is missing required key: {key}")
    for key in REQUIRED_SEGMENTATION_KEYS:
        if key not in spec["segmentation"]:
            raise ValueError(f"profile '{name}'.segmentation is missing required key: {key}")


def get_profile_spec(model_name: str) -> dict[str, Any]:
    """Return the raw profile spec for a canonical model name."""
    profiles = load_profiles()
    if model_name not in profiles:
        raise KeyError(
            f"Unknown model profile: {model_name}. Available: {sorted(profiles.keys())}"
        )
    return deepcopy(profiles[model_name])


def resolve_alias(name: str) -> str:
    """Resolve a model name or alias to its canonical profile key."""
    normalized = name.lower().replace("-", "_").replace(" ", "_")
    profiles = load_profiles()
    if normalized in profiles:
        return normalized
    for canonical, spec in profiles.items():
        if normalized in [str(a).lower() for a in spec.get("aliases", [])]:
            return canonical
    return normalized


# ---------------------------------------------------------------------------
# Token estimators (3 generic strategies)
# ---------------------------------------------------------------------------

def _estimate_plain_chars(text: str) -> int:
    return sum(1 for char in text if not char.isspace())


def _estimate_cjk_mixed(text: str) -> int:
    cjk_chars = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    latin_words = len(re.findall(r"[A-Za-z0-9']+", text))
    other_symbols = sum(
        1
        for char in text
        if not char.isspace() and not ("\u4e00" <= char <= "\u9fff") and not char.isalnum()
    )
    return max(
        1,
        math.ceil(cjk_chars * 0.8) + math.ceil(latin_words * 1.1) + math.ceil(other_symbols * 0.25),
    )


def _estimate_latin_words(text: str) -> int:
    latin_words = len(re.findall(r"[A-Za-z0-9']+", text))
    other_symbols = sum(1 for char in text if not char.isspace() and not char.isalnum())
    return max(1, latin_words + math.ceil(other_symbols * 0.3))


_TOKEN_ESTIMATORS: dict[str, Callable[[str], int]] = {
    "plain_chars": _estimate_plain_chars,
    "cjk_mixed": _estimate_cjk_mixed,
    "latin_words": _estimate_latin_words,
}


def get_token_estimator(strategy_id: str) -> Callable[[str], int]:
    """Return the token estimator for a strategy id (falls back to cjk_mixed)."""
    return _TOKEN_ESTIMATORS.get(strategy_id, _estimate_cjk_mixed)


# ---------------------------------------------------------------------------
# Profile builder (public API, signature-compatible with previous registry)
# ---------------------------------------------------------------------------

def build_model_service_profile(
    model_name: str,
    metadata: dict[str, Any] | None = None,
) -> ModelServiceProfile:
    """Build a ModelServiceProfile from the YAML single source of truth."""
    canonical = resolve_alias(model_name)
    spec = get_profile_spec(canonical)
    info = metadata or {}
    capabilities = spec["capabilities"]
    segmentation = spec["segmentation"]

    label = str(info.get("label") or spec.get("label") or canonical)
    requires_reference = bool(
        info.get("requires_reference", capabilities.get("requires_reference", False))
    )

    return ModelServiceProfile(
        canonical_name=canonical,
        label=label,
        version=str(spec.get("version") or "unknown"),
        requires_reference=requires_reference,
        supports_voice_instruction=bool(capabilities.get("voice_instruction", False)),
        supported_languages=list(info.get("supported_languages") or capabilities.get("languages") or []),
        min_reference_audio_seconds=float(capabilities.get("min_reference_audio_seconds") or 0.0),
        segmentation=SegmentationSettings(
            strategy_id=str(segmentation.get("estimator") or "cjk_mixed"),
            max_chars_per_segment=int(segmentation.get("max_chars_per_segment") or 280),
            max_estimated_duration_seconds=float(
                segmentation.get("max_estimated_duration_seconds") or 30.0
            ),
            max_input_tokens=(
                int(segmentation["max_input_tokens"])
                if segmentation.get("max_input_tokens") not in (None, "")
                else None
            ),
            target_input_tokens=(
                int(segmentation["target_input_tokens"])
                if segmentation.get("target_input_tokens") not in (None, "")
                else None
            ),
            force_chunk_chars=int(segmentation.get("force_chunk_chars") or 80),
            notes=str(segmentation.get("notes") or ""),
        ),
        task_inputs=deepcopy(spec.get("api_params") or []),
        capabilities=deepcopy(capabilities),
        runtime=deepcopy(spec.get("runtime") or {}),
        service=deepcopy(spec.get("service") or {}),
    )
