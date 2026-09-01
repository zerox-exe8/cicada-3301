"""
Kyro Discord Bot - Centralized Logging System
Provides colored terminal output and automatic rotating daily log files.
"""

from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
import colorlog


def setup_logger(name: str = "Kyro", log_level: int = logging.INFO) -> logging.Logger:
    """Configures and returns a custom logger with color support and file rotation."""
    logger = logging.getLogger(name)
    logger.setLevel(log_level)

    # Avoid duplicate handlers if setup_logger is called multiple times
    if logger.hasHandlers():
        return logger

    # 1. Console Handler with Colors
    console_handler = colorlog.StreamHandler()
    console_formatter = colorlog.ColoredFormatter(
        "%(asctime)s [%(log_color)s%(levelname)-8s%(reset)s] %(cyan)s%(name)s%(reset)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        log_colors={
            "DEBUG": "cyan",
            "INFO": "green",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "bold_red",
        },
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # 2. File Handler with Daily Rotation
    project_root = Path(__file__).resolve().parent.parent.parent
    logs_dir = project_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    file_handler = TimedRotatingFileHandler(
        filename=logs_dir / "kyro.log",
        when="midnight",
        interval=1,
        backupCount=14,  # Keep logs for 14 days
        encoding="utf-8",
    )
    file_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s (%(filename)s:%(lineno)d): %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    return logger


# Global default logger instance
logger = logging.getLogger("Kyro")
