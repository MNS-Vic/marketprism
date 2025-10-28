"""
Unified logging configuration for MarketPrism services.

- Uses structlog for structured, contextual logging
- Supports console (dev-friendly) and JSON (prod) renderers
- Exposes configure_logging() and get_logger() helpers

Environment variables:
  LOG_LEVEL   -> DEBUG | INFO | WARNING | ERROR | CRITICAL (default: INFO)
  JSON_LOGS   -> true | false (default: false)
"""
from __future__ import annotations

import logging
import os
import socket
from typing import Optional

import structlog

# Global service name bound at configuration time
_SERVICE_NAME: Optional[str] = None


def _get_log_level(default: str = "INFO") -> int:
    level = os.getenv("LOG_LEVEL", default).upper()
    return getattr(logging, level, logging.INFO)


def _get_json_logs(default: bool = False) -> bool:
    v = os.getenv("JSON_LOGS")
    if v is None:
        return default
    return str(v).lower() == "true"


def configure_logging(service_name: str, log_level: Optional[str] = None, json_logs: Optional[bool] = None) -> None:
    """Configure structlog and stdlib logging for the given service.

    Call once at process start, before creating loggers.
    """
    global _SERVICE_NAME
    _SERVICE_NAME = service_name

    level = _get_log_level(log_level or os.getenv("LOG_LEVEL", "INFO"))
    use_json = _get_json_logs(json_logs if json_logs is not None else _get_json_logs(False))

    # Set up stdlib logging base configuration
    logging.basicConfig(level=level, format="%(message)s")

    # Quieten noisy loggers if needed
    for noisy in ("aiohttp", "aiohttp.access", "urllib3"):
        logging.getLogger(noisy).setLevel(max(level, logging.WARNING))

    # Processors shared by both console and JSON
    shared_processors = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        # Ensure dict is JSON-serializable (e.g., datetime -> ISO8601)
        structlog.processors.UnicodeDecoder(),
    ]

    if use_json:
        final_processor = structlog.processors.JSONRenderer()
    else:
        final_processor = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            final_processor,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
        wrapper_class=structlog.stdlib.BoundLogger,
    )


def get_logger(module_name: str, **context) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger bound with standard fields.

    Example:
        logger = get_logger(__name__, service="monitoring-alerting")
    """
    base_context = {
        "service": _SERVICE_NAME or "unknown-service",
        "module": module_name,
        "hostname": socket.gethostname(),
        "pid": os.getpid(),
    }
    if context:
        base_context.update(context)
    return structlog.get_logger(module_name).bind(**base_context)


__all__ = ["configure_logging", "get_logger"]

