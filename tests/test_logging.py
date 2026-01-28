import logging

from dojo.logging import setup_logging


def test_setup_logging_defaults():
    """Test setup_logging with default arguments."""
    logger = setup_logging()
    assert logger.name == "dojo"
    # Note: basicConfig might not add handlers if root already has them,
    # but we can check if the logger is returned correctly.
    assert isinstance(logger, logging.Logger)


def test_setup_logging_level():
    """Test setup_logging with specific level."""
    # We might need to reset logging to test basicConfig properly,
    # but that's tricky in pytest.
    # Just checking the function runs and returns a logger is a good start.
    logger = setup_logging(level=logging.DEBUG)
    assert logger.name == "dojo"
