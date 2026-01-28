import logging
import sys


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure the project-wide logger."""
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    return logging.getLogger("dojo")


# Initialize with default
# Remove global side-effect
# logger = setup_logging()
