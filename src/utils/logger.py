"""Logging setup shared across the bot."""

import logging
import sys
from pathlib import Path


def setup_logger(
    name: str = "bot",
    level: str = "INFO",
    log_file: str | None = "logs/bot.log",
) -> logging.Logger:
    """Configure and return a logger that writes to console and (optionally) a file."""
    logger = logging.getLogger(name)
    if logger.handlers:  # already configured
        return logger

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"
    )

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    logger.addHandler(console)

    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_file)
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    return logger
