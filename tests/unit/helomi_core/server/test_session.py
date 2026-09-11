import asyncio

import pytest

from helomi_core.pipeline.domain import TranscriptionReadyEvent
from helomi_core.server.session import Session, SessionManager


@pytest.mark.asyncio
async def test_session_lifecycle_and_dispatch() -> None:
    session = Session(profile_id="p1")
    assert session.profile_id == "p1"
    assert session.id is not None

    events = []

    async def listener():
        async for evt in session.subscribe_event():
            events.append(evt)

    task = asyncio.create_task(listener())
    await asyncio.sleep(0.01)

    evt = TranscriptionReadyEvent(profile_id="p1", text="test text")
    session.dispatch_event(evt)
    await asyncio.sleep(0.01)

    assert len(events) == 1
    assert events[0] == evt

    session.close()
    await task


@pytest.mark.asyncio
async def test_session_manager_acquire_and_release() -> None:
    async with SessionManager() as sm:
        # Acquire profile
        s1 = await sm.acquire("p1")
        assert s1 is not None
        assert s1.profile_id == "p1"
        assert sm.get(s1.id) is s1

        # Attempt to acquire same profile returns None
        s2 = await sm.acquire("p1")
        assert s2 is None

        # Acquire different profile
        s3 = await sm.acquire("p2")
        assert s3 is not None

        # Dispatch event
        evt = TranscriptionReadyEvent(profile_id="p1", text="msg")
        sm.dispatch_event(evt)

        # Release s1
        await sm.release(s1)
        assert sm.get(s1.id) is None

        # Can acquire p1 again
        s1_again = await sm.acquire("p1")
        assert s1_again is not None

    # After exit stack closes, all sessions are closed
    assert sm.get(s1_again.id) is None
    assert sm.get(s3.id) is None
