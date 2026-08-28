from typing import Literal
from unittest.mock import MagicMock, patch

import pytest
from huggingface_hub.errors import (
    HFValidationError,
    LocalEntryNotFoundError,
    RepositoryNotFoundError,
)
from pydantic import ValidationError

from helomi_common.validation.config import AdapterConfig, AdapterExtractor, BaseConfig
from helomi_common.validation.hf import HFModel


class DummyAdapterConfig(BaseConfig):
    param: str = "default"


class CompoundConfig(AdapterConfig, AdapterExtractor[DummyAdapterConfig]):
    adapter: Literal["custom", "fallback"] = "custom"
    custom: DummyAdapterConfig | None = None
    fallback: DummyAdapterConfig | None = None


class ConfigWithoutAdapter(AdapterExtractor[DummyAdapterConfig]):
    pass


def test_base_config_immutability_and_extra_forbid():
    """Verify BaseConfig forbids extra attributes and prevents mutation."""
    config = DummyAdapterConfig(param="value")
    assert config.param == "value"

    with pytest.raises(ValidationError):
        DummyAdapterConfig(extra_field="invalid")  # type: ignore

    with pytest.raises(ValidationError):
        config.param = "new_value"  # type: ignore


def test_adapter_config_transform_adapters():
    """Verify model validator normalizes nested adapter dictionaries."""
    data = {
        "adapter": "custom",
        "custom": {"param": "custom_value"},
    }
    cfg = CompoundConfig.model_validate(data)
    assert cfg.adapter == "custom"
    assert cfg.custom is not None
    assert cfg.custom.param == "custom_value"


def test_adapter_extractor_success():
    """Verify extract_adapter returns the active adapter configuration."""
    cfg = CompoundConfig(
        adapter="custom",
        custom=DummyAdapterConfig(param="active"),
    )
    extracted = cfg.extract_adapter()
    assert extracted is not None
    assert extracted.param == "active"


def test_adapter_extractor_missing_adapter_config():
    """Verify extract_adapter handles missing adapter configuration appropriately."""
    cfg = CompoundConfig(
        adapter="custom",
        custom=None,
    )

    with pytest.raises(ValueError, match="Missing config for adapter: custom"):
        cfg.extract_adapter(require=True)

    assert cfg.extract_adapter(require=False) is None


def test_adapter_extractor_missing_adapter_field():
    """Verify extract_adapter raises AttributeError when class lacks adapter field."""
    cfg = ConfigWithoutAdapter()

    with pytest.raises(AttributeError, match="does not have an 'adapter' field"):
        cfg.extract_adapter(require=True)

    assert cfg.extract_adapter(require=False) is None


def test_hf_model_resolution_with_namespace(tmp_path):
    """Verify HFModel resolves repo ID with namespace."""
    model_dir = tmp_path / "models--org--repo"
    model_dir.mkdir()

    with patch(
        "helomi_common.validation.hf.snapshot_download", return_value=str(model_dir)
    ) as mock_snap:
        m1 = HFModel("org/repo")
        assert m1.id == "org/repo"
        assert m1.name == "repo"
        assert m1.namespace == "org"
        assert m1.path == model_dir
        assert str(m1) == "org/repo"
        mock_snap.assert_called_with(repo_id="org/repo", local_files_only=True)

        m2 = HFModel.model_validate({"id": "org/repo"})
        assert m2.id == "org/repo"
        assert m2.name == "repo"
        assert m2.namespace == "org"

        m_kw = HFModel(id="org/repo")
        assert m_kw.id == "org/repo"

        m3 = HFModel.model_validate(m1)
        assert m3 is m1


def test_hf_model_resolution_without_namespace(tmp_path):
    """Verify HFModel resolves repo ID without namespace."""
    model_dir = tmp_path / "models--simple-repo"
    model_dir.mkdir()

    with patch(
        "helomi_common.validation.hf.snapshot_download", return_value=str(model_dir)
    ):
        m = HFModel("simple-repo")
        assert m.id == "simple-repo"
        assert m.name == "simple-repo"
        assert m.namespace is None
        assert m.path == model_dir


def test_hf_model_invalid_input_type():
    """Verify HFModel raises ValueError on invalid input types or missing id key."""
    with pytest.raises(ValueError, match="Expected a valid Hugging Face repository ID"):
        HFModel.model_validate(12345)

    with pytest.raises(ValueError, match="Expected a valid Hugging Face repository ID"):
        HFModel.model_validate({"other_key": "val"})


def test_hf_model_exceptions():
    """Verify HFModel maps various Hub exceptions to descriptive ValueErrors."""
    with patch(
        "helomi_common.validation.hf.snapshot_download",
        side_effect=LocalEntryNotFoundError("Not cached"),
    ):
        with pytest.raises(ValueError, match="was not found in the local cache"):
            HFModel("org/not-cached")

    with patch(
        "helomi_common.validation.hf.snapshot_download",
        side_effect=RepositoryNotFoundError("Repo not found", response=MagicMock()),
    ):
        with pytest.raises(ValueError, match="Invalid Hugging Face model ID"):
            HFModel("org/non-existent")

    with patch(
        "helomi_common.validation.hf.snapshot_download",
        side_effect=HFValidationError("Invalid format"),
    ):
        with pytest.raises(ValueError, match="Invalid Hugging Face model ID"):
            HFModel("invalid@repo")

    with patch(
        "helomi_common.validation.hf.snapshot_download",
        side_effect=RuntimeError("Disk failure"),
    ):
        with pytest.raises(ValueError, match="Failed to resolve local"):
            HFModel("org/error-repo")
