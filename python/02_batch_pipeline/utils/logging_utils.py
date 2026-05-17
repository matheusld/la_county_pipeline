"""
logging_utils.py - Structured logging for the document triage pipeline.

Provides two loggers:
    1. pipeline_logger: General pipeline events, stage transitions, summaries.
       Writes to logs/pipeline.log and stdout.
    2. error_logger: Extraction failures, API errors, OCR issues.
       Writes to logs/errors.log.

Both loggers produce timestamped, structured output suitable for post-hoc
analysis. Every log entry includes the stage name and doc_id where applicable.

Usage:
    from utils.logging_utils import get_pipeline_logger, get_error_logger
    logger = get_pipeline_logger("./logs")
    logger.info("S01_DISCOVER | Found 540 files in scanned_docs")

    err_logger = get_error_logger("./logs")
    err_logger.error("S02_EXTRACT | doc_id=abc123 | pdfplumber failed | FileCorrupted")
"""

import logging
import os
from datetime import datetime, timezone


def get_pipeline_logger(log_dir: str) -> logging.Logger:
    """
    Returns a logger for general pipeline events.
    Creates log_dir if it doesn't exist.
    """
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger("triage_pipeline")
    if logger.handlers:
        return logger  # already configured

    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S"
    )

    # File handler
    fh = logging.FileHandler(os.path.join(log_dir, "pipeline.log"))
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    return logger


def get_error_logger(log_dir: str) -> logging.Logger:
    """
    Returns a logger for errors and failures.
    Separate file for easy post-hoc review of what went wrong.
    """
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger("triage_errors")
    if logger.handlers:
        return logger

    logger.setLevel(logging.WARNING)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S"
    )

    fh = logging.FileHandler(os.path.join(log_dir, "errors.log"))
    fh.setLevel(logging.WARNING)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger


def now_iso() -> str:
    """Returns current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()
