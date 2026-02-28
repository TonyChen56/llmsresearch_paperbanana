"""Tests for KIE provider registry wiring."""

from __future__ import annotations

import pytest

from paperbanana.core.config import Settings
from paperbanana.providers.registry import ProviderRegistry


def test_create_kie_vlm():
    """Registry creates KIE VLM with legacy default model."""
    settings = Settings(
        vlm_provider="kie",
        kie_api_key="test-key",
    )
    vlm = ProviderRegistry.create_vlm(settings)
    assert vlm.name == "kie"
    assert vlm.model_name == "gemini-2.5-flash"


def test_create_kie_vlm_with_override_model():
    """KIE VLM should use request/config override model when provided."""
    settings = Settings(
        vlm_provider="kie",
        vlm_model="gemini-2.5-pro",
        kie_api_key="test-key",
    )
    vlm = ProviderRegistry.create_vlm(settings)
    assert vlm.name == "kie"
    assert vlm.model_name == "gemini-2.5-pro"


def test_create_kie_nano_banana_image_gen():
    """Registry creates KIE image provider with legacy default model."""
    settings = Settings(
        image_provider="kie_nano_banana",
        kie_api_key="test-key",
    )
    gen = ProviderRegistry.create_image_gen(settings)
    assert gen.name == "kie_nano_banana"
    assert gen.model_name == "google/nano-banana"


def test_create_kie_image_gen_with_override_model():
    """KIE image provider should use request/config override model when provided."""
    settings = Settings(
        image_provider="kie_nano_banana",
        image_model="google/nano-banana-v2",
        kie_api_key="test-key",
    )
    gen = ProviderRegistry.create_image_gen(settings)
    assert gen.name == "kie_nano_banana"
    assert gen.model_name == "google/nano-banana-v2"


def test_create_kie_nano_banana_pro_image_gen():
    """Registry creates KIE Nano Banana Pro image provider with dedicated default model."""
    settings = Settings(
        image_provider="kie_nano_banana_pro",
        kie_api_key="test-key",
    )
    gen = ProviderRegistry.create_image_gen(settings)
    assert gen.name == "kie_nano_banana_pro"
    assert gen.model_name == "nano-banana-pro"


def test_create_kie_nano_banana_pro_image_gen_with_override_model():
    """KIE Nano Banana Pro provider should use override model when provided."""
    settings = Settings(
        image_provider="kie_nano_banana_pro",
        image_model="nano-banana-pro-custom",
        kie_api_key="test-key",
    )
    gen = ProviderRegistry.create_image_gen(settings)
    assert gen.name == "kie_nano_banana_pro"
    assert gen.model_name == "nano-banana-pro-custom"


def test_missing_kie_api_key_raises_helpful_error():
    """Missing KIE_API_KEY raises a help message for setup."""
    settings = Settings(vlm_provider="kie", kie_api_key=None)
    with pytest.raises(ValueError, match="KIE_API_KEY not found") as exc_info:
        ProviderRegistry.create_vlm(settings)
    error_msg = str(exc_info.value)
    assert "kie.ai/api-key" in error_msg
    assert "export KIE_API_KEY" in error_msg


def test_missing_kie_api_key_for_image_gen_raises_helpful_error():
    """Missing KIE_API_KEY for image provider raises a help message."""
    settings = Settings(image_provider="kie_nano_banana", kie_api_key=None)
    with pytest.raises(ValueError, match="KIE_API_KEY not found"):
        ProviderRegistry.create_image_gen(settings)
