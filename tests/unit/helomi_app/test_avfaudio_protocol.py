import pytest

from helomi_runtime.audio.avfaudio.protocol import (
    PROTOCOL_VERSION,
    HandshakePayload,
    MessageKind,
    WireFrame,
)


def test_avfaudio_protocol_new_request_id():
    """Verify _new_request_id generates sequential IDs and increments."""
    start_id = WireFrame._NEXT_REQUEST_ID
    id1 = WireFrame._new_request_id()
    id2 = WireFrame._new_request_id()

    assert id1 == start_id
    assert id2 == (start_id + 1) & 0xFFFFFFFF


def test_avfaudio_protocol_unpack_bool():
    """Verify unpack_bool unpacks 0/1, and raises RuntimeError on invalid."""
    frame_true = WireFrame(kind=MessageKind.READY, request_id=1, payload=b"\x01")
    assert frame_true.unpack_bool("test_prop") is True

    frame_false = WireFrame(kind=MessageKind.READY, request_id=2, payload=b"\x00")
    assert frame_false.unpack_bool("test_prop") is False

    frame_invalid = WireFrame(kind=MessageKind.READY, request_id=3, payload=b"\x02")
    with pytest.raises(RuntimeError, match="Native audio test_prop is invalid"):
        frame_invalid.unpack_bool("test_prop")

    frame_empty = WireFrame(kind=MessageKind.READY, request_id=4, payload=b"")
    with pytest.raises(RuntimeError, match="Native audio test_prop is invalid"):
        frame_empty.unpack_bool("test_prop")


def test_avfaudio_protocol_handshake_packed():
    """Verify HandshakePayload pack/unpack and version verification."""
    packed = HandshakePayload(version=PROTOCOL_VERSION)
    raw = packed.pack()
    unpacked = HandshakePayload.unpack(raw)
    assert unpacked.version == PROTOCOL_VERSION
    unpacked.verify()

    # Invalid length
    with pytest.raises(RuntimeError, match="expected 2 bytes"):
        HandshakePayload.unpack(b"\x01")

    # Mismatched version
    wrong_version = HandshakePayload(version=9999)
    with pytest.raises(
        RuntimeError, match="Unsupported avfaudio audio protocol version"
    ):
        wrong_version.verify()
