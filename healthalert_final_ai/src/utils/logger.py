"""Logging configuration for HealthAlert."""

import logging
import sys
from pathlib import Path
from typing import Optional


_CONFIGURED = False


def setup_logger(
    name: str = "healthalert",
    level: str = "INFO",
    log_file: Optional[str] = None,
    fmt: str = "%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s",
) -> logging.Logger:
    """Configure and return a logger.

    Only configures root handlers once to avoid duplicate log lines.
    """
    global _CONFIGURED
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    if not _CONFIGURED:
        formatter = logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S")

        # Console handler
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(formatter)
        logger.addHandler(ch)

        # File handler
        if log_file:
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            fh = logging.FileHandler(str(log_path), encoding="utf-8")
            fh.setFormatter(formatter)
            logger.addHandler(fh)

        _CONFIGURED = True

    return logger


def get_logger(name: str = "healthalert") -> logging.Logger:
    """Get an existing logger by name."""
    return logging.getLogger(name)
