"""
Configuration management for TTS Voice Cloning application.

Global settings live in config.yaml. Per-model data (catalog, capabilities,
segmentation, runtime, service endpoints) is data-driven from
model-profiles.yaml via src.model_profiles.registry.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import yaml
from loguru import logger

from src.exceptions import ConfigurationError


def _model_profiles_registry():
    """Lazy import to avoid circular imports at module load time."""
    from src.model_profiles import registry
    return registry


class Config:
    """Configuration manager for the application."""

    _instance: "Config" | None = None
    _config: Dict[str, Any] = {}

    def __new__(cls) -> "Config":
        """Singleton pattern to ensure single config instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def load(self, config_path: str = "config.yaml") -> None:
        """
        Load configuration from YAML file.

        Args:
            config_path: Path to the configuration file.

        Raises:
            ConfigurationError: If the file cannot be loaded or parsed.
        """
        path = Path(config_path)

        if not path.exists():
            raise ConfigurationError(
                f"Config file not found: {config_path}",
                {"file": config_path}
            )

        try:
            with open(path, "r", encoding="utf-8") as f:
                loaded_config = yaml.safe_load(f) or {}
            if not isinstance(loaded_config, dict):
                raise ConfigurationError(
                    "Configuration root must be a mapping",
                    {"file": config_path}
                )

            self._config = loaded_config
            self._validate_config()
            logger.info(f"Configuration loaded from {config_path}")
        except yaml.YAMLError as e:
            raise ConfigurationError(
                f"Failed to parse configuration file: {e}",
                {"file": config_path}
            )
        except ConfigurationError:
            raise
        except Exception as e:
            raise ConfigurationError(
                f"Failed to load configuration file: {e}",
                {"file": config_path}
            )

    def _validate_config(self) -> None:
        """Validate required global configuration keys and model profiles."""
        for key in (
            "app.name",
            "app.version",
            "model.default",
            "model.cache_dir",
            "output.default_dir",
            "output.format",
            "output.sample_rate",
            "voice_profiles.storage_dir",
            "logging.level",
            "logging.dir",
            "logging.retention",
            "logging.max_size",
            "gui.host",
            "gui.port",
            "gui.share",
            "service.host",
            "service.port",
            "service.data_dir",
            "service.max_chars_per_segment",
            "service.max_estimated_duration_seconds",
            "service.reset_interrupted_tasks_on_start",
            "service.poll_interval_seconds",
            "model_services.request_timeout_seconds",
        ):
            self.require(key)

        # Validate model-profiles.yaml and derived catalog/endpoints.
        catalog = self.models_catalog
        if not catalog:
            raise ConfigurationError("model-profiles.yaml must define at least one profile")

        default_model = self.model_default
        if default_model not in catalog:
            raise ConfigurationError(
                f"Default model '{default_model}' is not defined in model-profiles.yaml"
            )

        _ = self.models_enabled
        endpoints = self.model_service_endpoints
        for model_name in self.models_enabled:
            if model_name not in endpoints:
                raise ConfigurationError(
                    f"Missing service.port for enabled model profile: {model_name}"
                )

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value using dot notation.

        Args:
            key: Configuration key (e.g., "model.default").
            default: Default value if key not found.

        Returns:
            Configuration value or default.
        """
        keys = key.split(".")
        value = self._config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def require(self, key: str) -> Any:
        """Get a required configuration value or raise ConfigurationError."""
        sentinel = object()
        value = self.get(key, sentinel)
        if value is sentinel:
            raise ConfigurationError(f"Missing required configuration key: {key}")
        return value

    def _require_mapping(self, key: str) -> Dict[str, Any]:
        """Get a required mapping value from configuration."""
        value = self.require(key)
        if not isinstance(value, dict):
            raise ConfigurationError(f"{key} must be a mapping")
        return value

    # ------------------------------------------------------------- app / dirs

    @property
    def app_name(self) -> str:
        """Get the configured application name."""
        return str(self.require("app.name"))

    @property
    def app_version(self) -> str:
        """Get the configured application version."""
        return str(self.require("app.version"))

    @property
    def model_default(self) -> str:
        """Get the default model name."""
        return str(self.require("model.default"))

    @property
    def model_cache_dir(self) -> Path:
        """Get the model cache directory."""
        return Path(self.require("model.cache_dir"))

    @property
    def output_dir(self) -> Path:
        """Get the output directory."""
        return Path(self.require("output.default_dir"))

    @property
    def voice_profiles_dir(self) -> Path:
        """Get the voice profiles directory."""
        return Path(self.require("voice_profiles.storage_dir"))

    @property
    def log_dir(self) -> Path:
        """Get the log directory."""
        return Path(self.require("logging.dir"))

    @property
    def log_level(self) -> str:
        """Get the logging level."""
        return str(self.require("logging.level"))

    @property
    def log_retention(self) -> str:
        """Get log retention policy."""
        return str(self.require("logging.retention"))

    @property
    def log_max_size(self) -> str:
        """Get log rotation size."""
        return str(self.require("logging.max_size"))

    @property
    def gui_port(self) -> int:
        """Get the GUI server port."""
        return int(self.require("gui.port"))

    @property
    def gui_host(self) -> str:
        """Get the GUI server host."""
        return str(self.require("gui.host"))

    @property
    def gui_share(self) -> bool:
        """Get the GUI share flag."""
        return bool(self.require("gui.share"))

    @property
    def service_host(self) -> str:
        """Get the service host address."""
        return str(self.require("service.host"))

    @property
    def service_port(self) -> int:
        """Get the service port."""
        return int(self.require("service.port"))

    @property
    def data_dir(self) -> Path:
        """Get the service data directory."""
        return Path(self.require("service.data_dir"))

    @property
    def service_max_chars_per_segment(self) -> int:
        """Get maximum chars per text segment."""
        return int(self.require("service.max_chars_per_segment"))

    @property
    def service_max_estimated_duration_seconds(self) -> int:
        """Get maximum estimated duration per segment."""
        return int(self.require("service.max_estimated_duration_seconds"))

    @property
    def service_reset_interrupted_tasks_on_start(self) -> bool:
        """Get startup recovery behavior for interrupted tasks."""
        return bool(self.require("service.reset_interrupted_tasks_on_start"))

    @property
    def service_poll_interval_seconds(self) -> int:
        """Get frontend polling interval for task updates."""
        return int(self.require("service.poll_interval_seconds"))

    # ---------------------------------------------- model data (profile-driven)

    @property
    def models_catalog(self) -> Dict[str, Dict[str, Any]]:
        """Model catalog derived from model-profiles.yaml."""
        registry = _model_profiles_registry()
        catalog: Dict[str, Dict[str, Any]] = {}
        for name, spec in registry.load_profiles().items():
            capabilities = spec.get("capabilities") or {}
            catalog[name] = {
                "label": spec.get("label", name),
                "description": spec.get("description", ""),
                "enabled": bool(spec.get("enabled", True)),
                "implemented": True,
                "requires_reference": bool(capabilities.get("requires_reference", True)),
                "aliases": list(spec.get("aliases", [])),
                "source": spec.get("source"),
                "version": spec.get("version"),
            }
        return catalog

    @property
    def models_enabled(self) -> list[str]:
        """Get the enabled canonical model names."""
        enabled_models = [
            name
            for name, metadata in self.models_catalog.items()
            if isinstance(metadata, dict) and metadata.get("enabled") is True
        ]
        if not enabled_models:
            raise ConfigurationError(
                "At least one profile in model-profiles.yaml must set enabled: true"
            )
        if self.model_default not in enabled_models:
            raise ConfigurationError(
                f"Default model '{self.model_default}' must set enabled: true in model-profiles.yaml"
            )
        return enabled_models

    @property
    def model_service_request_timeout_seconds(self) -> int:
        """Get the request timeout for remote model services."""
        return int(self.require("model_services.request_timeout_seconds"))

    @property
    def model_service_endpoints(self) -> Dict[str, Dict[str, Any]]:
        """
        Remote model service endpoints, derived from profiles' service section.
        Optional model_services.endpoints entries in config.yaml override
        generated base_url values.
        """
        registry = _model_profiles_registry()
        endpoints: Dict[str, Dict[str, Any]] = {}
        for name, spec in registry.load_profiles().items():
            service = spec.get("service") or {}
            host = str(service.get("host") or "10.0.13.209")
            port = service.get("port")
            entry: Dict[str, Any] = {"base_url": f"http://{host}:{port}"}
            for key in ("container", "requirements", "image_env", "internal_port"):
                if key in service:
                    entry[key] = service[key]
            endpoints[name] = entry

        for name, metadata in (self.get("model_services.endpoints") or {}).items():
            normalized_name = str(name).lower().replace("-", "_").replace(" ", "_")
            merged = dict(endpoints.get(normalized_name, {}))
            if isinstance(metadata, dict):
                merged.update(metadata)
            endpoints[normalized_name] = merged
        return endpoints

    def model_service_url(self, model_name: str) -> str:
        """Resolve the remote base URL for a model service, honoring env overrides."""
        normalized_name = str(model_name).lower().replace("-", "_").replace(" ", "_")
        env_key = f"VOICECLONER_MODEL_SERVICE_{normalized_name.upper()}_URL"
        env_value = os.getenv(env_key, "").strip()
        if env_value:
            return env_value

        endpoints = self.model_service_endpoints
        entry = endpoints.get(normalized_name)
        if entry is None:
            raise ConfigurationError(
                f"No service endpoint found for model: {normalized_name}"
            )
        base_url = str(entry.get("base_url", "")).strip()
        if not base_url:
            raise ConfigurationError(
                f"Missing base_url for model service: {normalized_name}"
            )
        return base_url

    # ------------------------------------------------- adapter runtime settings

    def get_model_runtime(self, model_name: str) -> Dict[str, Any]:
        """Get the runtime constructor settings for a model profile."""
        registry = _model_profiles_registry()
        canonical = registry.resolve_alias(model_name)
        spec = registry.get_profile_spec(canonical)
        runtime = spec.get("runtime") or {}
        if not isinstance(runtime, dict):
            raise ConfigurationError(f"profile '{canonical}'.runtime must be a mapping")
        return dict(runtime)

    @property
    def xtts_settings(self) -> Dict[str, Any]:
        """XTTS adapter runtime settings (kept for src/models/xtts.py)."""
        return self.get_model_runtime("xtts")


# Global config instance
config = Config()
