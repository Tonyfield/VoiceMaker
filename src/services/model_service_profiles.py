"""HTTP helpers for fetching remote model-service profiles."""

from __future__ import annotations

import httpx

from src.config import config
from src.exceptions import ConfigurationError, ModelServiceError
from src.model_profiles import ModelServiceProfile


def _extract_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = None

    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str) and detail.strip():
            return detail.strip()

    return response.text.strip() or f"HTTP {response.status_code}"


def fetch_model_profile(model_name: str) -> ModelServiceProfile:
    try:
        service_url = config.model_service_url(model_name).rstrip("/")
    except ConfigurationError as exc:
        raise ModelServiceError(str(exc), {"model": model_name}) from exc

    try:
        with httpx.Client(
            base_url=service_url,
            timeout=config.model_service_request_timeout_seconds,
        ) as client:
            response = client.get("/api/profile")
    except httpx.HTTPError as exc:
        raise ModelServiceError(
            f"Failed to fetch remote model profile for '{model_name}': {exc}",
            {"model": model_name, "service_url": service_url},
        ) from exc

    if response.is_error:
        raise ModelServiceError(
            f"Remote model profile '{model_name}' returned {response.status_code}: {_extract_error(response)}",
            {"model": model_name, "service_url": service_url, "status_code": response.status_code},
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise ModelServiceError(
            f"Remote model profile '{model_name}' returned invalid JSON",
            {"model": model_name, "service_url": service_url},
        ) from exc

    return ModelServiceProfile.from_dict(payload)


async def fetch_model_profile_async(
    client: httpx.AsyncClient,
    model_name: str,
) -> ModelServiceProfile:
    service_url = config.model_service_url(model_name).rstrip("/")
    try:
        response = await client.get(f"{service_url}/api/profile")
    except httpx.HTTPError as exc:
        raise ModelServiceError(
            f"Failed to fetch remote model profile for '{model_name}': {exc}",
            {"model": model_name, "service_url": service_url},
        ) from exc

    if response.is_error:
        raise ModelServiceError(
            f"Remote model profile '{model_name}' returned {response.status_code}: {_extract_error(response)}",
            {"model": model_name, "service_url": service_url, "status_code": response.status_code},
        )

    return ModelServiceProfile.from_dict(response.json())