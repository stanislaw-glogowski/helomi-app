import pytest

from helomi_core.server.session import ProfileLockedError, SessionManager
from helomi_core.speech import ProfileActivated, TranscriptionReady


@pytest.mark.asyncio
async def test_session_manager_acquire_and_release() -> None:
    sm = SessionManager()
    assert sm.active_sessions_count == 0

    session = await sm.acquire("profile_1")
    assert session.profile_id == "profile_1"
    assert sm.active_sessions_count == 1
    assert sm.get(session.id) is session

    # Attempt to acquire same profile should raise ProfileLockedError
    with pytest.raises(ProfileLockedError) as exc_info:
        await sm.acquire("profile_1")
    assert "Profile 'profile_1' is already locked" in str(exc_info.value)

    # Release session
    await sm.release(session.id)
    assert sm.active_sessions_count == 0
    assert sm.get(session.id) is None
    # Queue should receive None sentinel
    sentinel = await session.queue.get()
    assert sentinel is None

    # Releasing non-existent session should be a no-op
    await sm.release("unknown_id")


@pytest.mark.asyncio
async def test_session_manager_dispatch_event() -> None:
    sm = SessionManager()
    session1 = await sm.acquire("profile_1")
    session2 = await sm.acquire("profile_2")

    # Dispatch event for profile_1
    evt1 = TranscriptionReady(profile_id="profile_1", text="Hello 1")
    sm.dispatch_event(evt1)

    # Dispatch event for profile_2
    evt2 = ProfileActivated(profile_id="profile_2")
    sm.dispatch_event(evt2)

    # Dispatch event for non-existent profile_3
    evt3 = TranscriptionReady(profile_id="profile_3", text="Ignored")
    sm.dispatch_event(evt3)

    assert await session1.queue.get() == evt1
    assert await session2.queue.get() == evt2
    assert session1.queue.empty()
    assert session2.queue.empty()

    await sm.release(session1.id)
    await sm.release(session2.id)


@pytest.mark.asyncio
async def test_session_manager_close_all() -> None:
    sm = SessionManager()
    session1 = await sm.acquire("p1")
    session2 = await sm.acquire("p2")
    assert sm.active_sessions_count == 2

    await sm.close_all()
    assert sm.active_sessions_count == 0
    assert await session1.queue.get() is None
    assert await session2.queue.get() is None
