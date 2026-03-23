"""Logging configuration for Dojo.

Provides both human-readable (Rich) and structured (JSON) logging formats.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import TextIO


class JsonFormatter(logging.Formatter):
    """JSON log formatter for structured logging.

    Outputs each log record as a single-line JSON object with:
    - timestamp: ISO 8601 format with timezone
    - level: Log level name
    - logger: Logger name
    - message: Formatted message

    Additional fields are included if present in the log record.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_entry: dict[str, object] = {
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add extra fields if present on the record
        extra_fields = [
            "file",
            "duration_ms",
            "output_count",
            "source_count",
            "config_path",
        ]
        for field in extra_fields:
            if hasattr(record, field):
                value: object = getattr(record, field)
                log_entry[field] = value

        # Include exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str)


def setup_logging(
    level: int = logging.INFO,
    *,
    json_output: bool = False,
    stream: TextIO | None = None,
) -> logging.Logger:
    """Configure the project-wide logger.

    Args:
        level: Logging level (default: INFO)
        json_output: If True, output logs as JSON for machine parsing
        stream: Output stream (defaults to stdout)

    Returns:
        Configured logger instance

    """
    if stream is None:
        stream = sys.stdout

    # Remove existing handlers to avoid duplicates
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(stream)

    if json_output:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

    logging.basicConfig(
        level=level,
        handlers=[handler],
        force=True,
    )

    return logging.getLogger("dojo")
