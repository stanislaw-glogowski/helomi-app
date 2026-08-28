from dataclasses import dataclass

from helomi_common.foundation.adapter import AbstractAdapter


@dataclass
class DummyConfig:
    setting: str


class DummyAdapter(AbstractAdapter[DummyConfig]):
    """Concrete adapter for unit testing."""

    pass


def test_abstract_adapter_stores_config():
    """Verify that AbstractAdapter sets config and inherits component lifecycle."""
    cfg = DummyConfig(setting="test_value")
    adapter = DummyAdapter(cfg)

    assert adapter._config == cfg
    assert not adapter._is_open

    with adapter:
        assert adapter._is_open

    assert not adapter._is_open
