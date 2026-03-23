import io
import json
import logging
import sys

from dojo.logging import JsonFormatter, setup_logging


# Test constants
EXPECTED_DURATION_MS = 42
EXPECTED_OUTPUT_COUNT = 5


def test_setup_logging_defaults():
    """Test setup_logging with default arguments."""
    logger = setup_logging()
    assert logger.name == "dojo"
    assert isinstance(logger, logging.Logger)


def test_setup_logging_level():
    """Test setup_logging with specific level."""
    logger = setup_logging(level=logging.DEBUG)
    assert logger.name == "dojo"


def test_setup_logging_json_output():
    """Test setup_logging with JSON output enabled."""
    stream = io.StringIO()
    logger = setup_logging(json_output=True, stream=stream)

    # Log a message
    logger.info("Test message")

    # Get output
    output = stream.getvalue()
    assert output.strip()  # Non-empty

    # Parse as JSON
    log_entry = json.loads(output.strip())
    assert log_entry["message"] == "Test message"
    assert log_entry["level"] == "INFO"
    assert "timestamp" in log_entry
    assert "logger" in log_entry


def test_json_formatter_basic():
    """Test JsonFormatter produces valid JSON."""
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="Hello %s",
        args=("world",),
        exc_info=None,
    )

    output = formatter.format(record)
    data = json.loads(output)

    assert data["message"] == "Hello world"
    assert data["level"] == "INFO"
    assert data["logger"] == "test"
    assert "timestamp" in data


def test_json_formatter_extra_fields():
    """Test JsonFormatter includes extra fields."""
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="Processing file",
        args=(),
        exc_info=None,
    )
    # Add extra fields
    record.file = "/path/to/file.md"
    record.duration_ms = EXPECTED_DURATION_MS
    record.output_count = EXPECTED_OUTPUT_COUNT

    output = formatter.format(record)
    data = json.loads(output)

    assert data["file"] == "/path/to/file.md"
    assert data["duration_ms"] == EXPECTED_DURATION_MS
    assert data["output_count"] == EXPECTED_OUTPUT_COUNT


def _create_test_exception() -> tuple[type, BaseException, object]:
    """Create a test exception and return its exc_info.

    This helper intentionally raises and catches an exception to capture
    exc_info for testing the JsonFormatter's exception handling.
    """
    try:
        msg = "Test error"
        raise ValueError(msg)
    except ValueError:
        return sys.exc_info()


def test_json_formatter_exception():
    """Test JsonFormatter includes exception info."""
    formatter = JsonFormatter()
    exc_info = _create_test_exception()

    record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname="test.py",
        lineno=1,
        msg="An error occurred",
        args=(),
        exc_info=exc_info,
    )

    output = formatter.format(record)
    data = json.loads(output)

    assert data["level"] == "ERROR"
    assert "exception" in data
    assert "ValueError: Test error" in data["exception"]
