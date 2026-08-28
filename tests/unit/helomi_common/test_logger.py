import io
import sys

from helomi_common.logger.configure import LogLevel, configure_logger
from helomi_common.logger.proxy import TaggedStreamProxy


def test_log_level_enum():
    """Verify LogLevel values."""
    assert LogLevel.DEBUG == "debug"
    assert LogLevel.INFO == "info"
    assert LogLevel.WARNING == "warning"
    assert LogLevel.ERROR == "error"


def test_tagged_stream_proxy_tagging_and_filtering():
    """Test TaggedStreamProxy message filtering and unwrapping."""
    buffer = io.StringIO()
    proxy = TaggedStreamProxy(buffer, skip_untagged=True)

    # Untagged message should be skipped when skip_untagged is True
    proxy.write("Untagged message")
    assert buffer.getvalue() == ""

    # Tagged message should have tag stripped and be written
    tagged = TaggedStreamProxy.tag("Tagged message\n")
    proxy.write(tagged)
    assert buffer.getvalue() == "Tagged message\n"

    # writelines should iterate and process lines
    proxy.writelines([TaggedStreamProxy.tag("Line 1\n"), "Untagged Line 2\n"])
    assert buffer.getvalue() == "Tagged message\nLine 1\n"


def test_tagged_stream_proxy_traceback_passthrough():
    """Verify traceback messages disable filtering."""
    buffer = io.StringIO()
    proxy = TaggedStreamProxy(buffer, skip_untagged=True)

    tb_msg = "Traceback (most recent call last):\n  File 'test.py', line 1\n"
    proxy.write(tb_msg)
    assert tb_msg in buffer.getvalue()
    assert not proxy._enabled

    # Once disabled, subsequent untagged messages pass through
    proxy.write("Follow up error text")
    assert "Follow up error text" in buffer.getvalue()


def test_tagged_stream_proxy_delegated_properties():
    """Test delegate stream attributes such as flush, encoding, and isatty."""
    buffer = io.StringIO()
    proxy = TaggedStreamProxy(buffer)

    proxy.flush()
    assert proxy.isatty() == buffer.isatty()
    assert proxy.encoding == getattr(buffer, "encoding", "utf-8")
    assert proxy.errors == getattr(buffer, "errors", None)


def test_configure_logger_with_callable():
    """Test logger configuration with a callable log formatter."""
    original_stderr = sys.stderr
    sink = io.StringIO()
    try:

        def formatter(record) -> str:
            return f"CUSTOM | {record['message']}"

        logger = configure_logger(
            formatter, LogLevel.INFO, skip_untagged=True, sink=sink
        )
        assert logger is not None
        assert isinstance(sys.stderr, TaggedStreamProxy)
        logger.info("Hello world")
        assert "CUSTOM | Hello world" in sink.getvalue()
    finally:
        sys.stderr = original_stderr


def test_configure_logger_with_string():
    """Test logger configuration with a string format."""
    original_stderr = sys.stderr
    sink = io.StringIO()
    try:
        logger = configure_logger(
            "<level>{message}</level>", LogLevel.DEBUG, skip_untagged=False, sink=sink
        )
        assert logger is not None
        logger.debug("Debug msg")
        assert "Debug msg" in sink.getvalue()
    finally:
        sys.stderr = original_stderr
