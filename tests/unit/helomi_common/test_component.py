import pytest

from helomi_common.foundation.component import (
    AbstractAsyncComponent,
    AbstractComponent,
    BaseComponent,
)


class SampleComponent(BaseComponent):
    """Concrete subclass for testing BaseComponent."""

    pass


class ConcreteSyncComponent(AbstractComponent):
    """Concrete synchronous component for testing lifecycle."""

    def __init__(self, is_quiet: bool = False) -> None:
        super().__init__(is_quiet=is_quiet)
        self.opened = False
        self.closed = False
        self.fail_on_open = False
        self.fail_on_close = False

    def _do_open(self) -> None:
        if self.fail_on_open:
            raise ValueError("Open failed")
        self.opened = True

    def _do_close(self) -> None:
        if self.fail_on_close:
            raise RuntimeError("Close failed")
        self.closed = True

    def perform_action(self) -> str:
        self._require_open()
        return "action_performed"


class ConcreteAsyncComponent(AbstractAsyncComponent):
    """Concrete asynchronous component for testing lifecycle."""

    def __init__(self, is_quiet: bool = False) -> None:
        super().__init__(is_quiet=is_quiet)
        self.lifecycle_steps: list[str] = []
        self.fail_step: str | None = None

    async def _pre_open(self) -> None:
        if self.fail_step == "pre_open":
            raise ValueError("Failed in pre_open")
        self.lifecycle_steps.append("pre_open")

    async def _do_open(self) -> None:
        if self.fail_step == "do_open":
            raise ValueError("Failed in do_open")
        self.lifecycle_steps.append("do_open")

    async def _post_open(self) -> None:
        if self.fail_step == "post_open":
            raise ValueError("Failed in post_open")
        self.lifecycle_steps.append("post_open")

    async def _pre_close(self) -> None:
        if self.fail_step == "pre_close":
            raise RuntimeError("Failed in pre_close")
        self.lifecycle_steps.append("pre_close")

    async def _do_close(self) -> None:
        if self.fail_step == "do_close":
            raise RuntimeError("Failed in do_close")
        self.lifecycle_steps.append("do_close")

    async def _post_close(self) -> None:
        if self.fail_step == "post_close":
            raise RuntimeError("Failed in post_close")
        self.lifecycle_steps.append("post_close")

    def perform_action(self) -> str:
        self._require_open()
        return "async_action_performed"


def test_base_component_initialization():
    """Verify BaseComponent sets component name and bound logger."""
    component = SampleComponent()
    assert component.__component__ == "SampleComponent"
    assert component._logger is not None


def test_abstract_sync_component_lifecycle():
    """Test standard open and close lifecycle for synchronous component."""
    comp = ConcreteSyncComponent()

    with pytest.raises(RuntimeError, match="ConcreteSyncComponent is not open"):
        comp.perform_action()

    comp.open()
    assert comp.opened
    assert comp._is_open
    assert comp.perform_action() == "action_performed"

    # Repeated open should raise RuntimeError
    with pytest.raises(RuntimeError, match="ConcreteSyncComponent is already open"):
        comp.open()

    comp.close()
    assert comp.closed
    assert not comp._is_open

    # Repeated close is idempotent and does not raise
    comp.close()


def test_abstract_sync_component_context_manager():
    """Test AbstractComponent used as a context manager."""
    with ConcreteSyncComponent() as comp:
        assert comp._is_open
        assert comp.perform_action() == "action_performed"
    assert not comp._is_open
    assert comp.closed


def test_abstract_sync_component_open_failure():
    """Verify that failure in _do_open triggers cleanup and re-raises."""
    comp = ConcreteSyncComponent()
    comp.fail_on_open = True

    with pytest.raises(ValueError, match="Open failed"):
        comp.open()

    assert not comp._is_open


def test_abstract_sync_component_close_failure_logged():
    """Verify that exception in _do_close during close() is swallowed and logged."""
    comp = ConcreteSyncComponent()
    comp.open()
    comp.fail_on_close = True

    # Should not raise exception
    comp.close()
    assert not comp._is_open


@pytest.mark.asyncio
async def test_abstract_async_component_lifecycle():
    """Test full async lifecycle: pre_open -> do_open -> post_open and close steps."""
    comp = ConcreteAsyncComponent()

    with pytest.raises(RuntimeError, match="ConcreteAsyncComponent is not open"):
        comp.perform_action()

    await comp.open()
    assert comp._is_open
    assert comp.lifecycle_steps == ["pre_open", "do_open", "post_open"]
    assert comp.perform_action() == "async_action_performed"

    with pytest.raises(RuntimeError, match="ConcreteAsyncComponent is already open"):
        await comp.open()

    await comp.close()
    assert not comp._is_open
    assert comp.lifecycle_steps == [
        "pre_open",
        "do_open",
        "post_open",
        "pre_close",
        "do_close",
        "post_close",
    ]

    # Repeated close is idempotent
    await comp.close()


@pytest.mark.asyncio
async def test_abstract_async_component_context_manager():
    """Test AbstractAsyncComponent with async context manager."""
    async with ConcreteAsyncComponent() as comp:
        assert comp._is_open
        assert comp.perform_action() == "async_action_performed"

    assert not comp._is_open


@pytest.mark.asyncio
async def test_abstract_async_component_open_failure():
    """Verify open failure in async component calls close and re-raises."""
    comp = ConcreteAsyncComponent()
    comp.fail_step = "do_open"

    with pytest.raises(ValueError, match="Failed in do_open"):
        await comp.open()

    assert not comp._is_open


@pytest.mark.asyncio
async def test_abstract_async_component_close_exceptions_handled():
    """Verify errors occurring in async close steps are captured and logged."""
    comp = ConcreteAsyncComponent()
    await comp.open()
    comp.fail_step = "do_close"

    # Should handle error gracefully without re-raising to caller
    await comp.close()
    assert not comp._is_open
