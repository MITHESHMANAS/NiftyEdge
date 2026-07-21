"""
src/etl/logging_setup.py

Structured logging for the ETL pipeline. Writes to logs/etl.log (rotating,
so repeated `make load` runs don't grow the file unboundedly) and echoes
INFO+ to the console.

All loggers returned by get_logger() are children of a single 'n100_etl'
root logger so they share its handlers via Python's normal logger
hierarchy (get_logger('src.etl.loader') -> 'n100_etl.src.etl.loader').
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from src.etl.config import LOG_LEVEL, LOG_PATH

_BASE_LOGGER_NAME = "n100_etl"
_CONFIGURED = False


def _configure_base_logger() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    LOG_PATH.mkdir(parents=True, exist_ok=True)
    log_file = LOG_PATH / "etl.log"

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=3)
    file_handler.setFormatter(fmt)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)

    base = logging.getLogger(_BASE_LOGGER_NAME)
    base.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    base.addHandler(file_handler)
    base.addHandler(console_handler)
    base.propagate = False

    _CONFIGURED = True


def get_logger(name: str = _BASE_LOGGER_NAME) -> logging.Logger:
    """Returns a logger under the 'n100_etl' hierarchy so it inherits the
    file + console handlers configured on the base logger. Pass __name__
    from the calling module for clear log attribution."""
    _configure_base_logger()
    if name == _BASE_LOGGER_NAME or name.startswith(f"{_BASE_LOGGER_NAME}."):
        return logging.getLogger(name)
    return logging.getLogger(f"{_BASE_LOGGER_NAME}.{name}")
