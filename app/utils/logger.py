"""
Structured logging module with JSON formatting and credential filtering.
"""

import json
import logging
import logging.handlers
import os
import re
import sys
import time
import tracemalloc
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


class CredentialFilter(logging.Filter):
    """Filters out sensitive credentials from log messages."""

    SENSITIVE_PATTERNS = [
        (re.compile(r"(password|passwd|pwd)\s*[=:]\s*\S+", re.IGNORECASE), r"\1=***REDACTED***"),
        (re.compile(r"(username|user|login)\s*[=:]\s*\S+", re.IGNORECASE), r"\1=***REDACTED***"),
        (re.compile(r"(token|secret|key|api_key|apikey)\s*[=:]\s*\S+", re.IGNORECASE), r"\1=***REDACTED***"),
        (re.compile(r"(cookie|session)\s*[=:]\s*\S+", re.IGNORECASE), r"\1=***REDACTED***"),
        (re.compile(r"(Bearer)\s+\S+", re.IGNORECASE), r"\1 ***REDACTED***"),
        (re.compile(r"(Basic)\s+\S+", re.IGNORECASE), r"\1 ***REDACTED***"),
    ]

    def __init__(self, name: str = "") -> None:
        super().__init__(name)

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            for pattern, replacement in self.SENSITIVE_PATTERNS:
                record.msg = pattern.sub(replacement, record.msg)
        if record.args and isinstance(record.args, dict):
            filtered_args = {}
            for key, value in record.args.items():
                if any(
                    sensitive in key.lower()
                    for sensitive in ["password", "user", "token", "secret", "key", "cookie"]
                ):
                    filtered_args[key] = "***REDACTED***"
                else:
                    filtered_args[key] = value
            record.args = filtered_args
        return True


class PerformanceFilter(logging.Filter):
    """Adds memory usage information to log records."""

    def __init__(self, name: str = "") -> None:
        super().__init__(name)
        if not tracemalloc.is_tracing():
            tracemalloc.start()

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            current, peak = tracemalloc.get_traced_memory()
            record.memory_mb = round(current / 1024 / 1024, 2)
            record.peak_memory_mb = round(peak / 1024 / 1024, 2)
        except Exception:
            record.memory_mb = 0.0
            record.peak_memory_mb = 0.0
        return True


class JSONFormatter(logging.Formatter):
    """JSON log formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "message": record.getMessage(),
        }

        if hasattr(record, "memory_mb"):
            log_entry["memory_mb"] = record.memory_mb
            log_entry["peak_memory_mb"] = record.peak_memory_mb

        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """Console-friendly formatter with colors."""

    COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[35m",
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, self.RESET)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return (
            f"{color}{timestamp} [{record.levelname:8s}] "
            f"{record.module}:{record.funcName}:{record.lineno} "
            f"- {record.getMessage()}{self.RESET}"
        )


def get_logger(name: str, log_dir: Optional[str] = None) -> logging.Logger:
    """
    Get a configured logger instance.

    Args:
        name: Logger name (typically module name)
        log_dir: Directory for log files

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    if log_dir is None:
        log_dir = str(Path(__file__).resolve().parent.parent.parent / "logs")

    os.makedirs(log_dir, exist_ok=True)

    credential_filter = CredentialFilter()
    performance_filter = PerformanceFilter()

    json_handler = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, "app.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    json_handler.setLevel(logging.DEBUG)
    json_handler.setFormatter(JSONFormatter())
    json_handler.addFilter(credential_filter)
    json_handler.addFilter(performance_filter)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(ConsoleFormatter())
    console_handler.addFilter(credential_filter)

    error_handler = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, "error.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(JSONFormatter())
    error_handler.addFilter(credential_filter)

    logger.addHandler(json_handler)
    logger.addHandler(console_handler)
    logger.addHandler(error_handler)

    return logger
