"""Logging factory — single responsibility: provide a named logger."""

from __future__ import annotations

import logging

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s – %(message)s"


def _configure_root() -> None:
    logging.basicConfig(level=logging.INFO, format=_LOG_FORMAT)


_configure_root()


def get_logger(name: str = "hydramem") -> logging.Logger:
    """Return a named logger for the given module."""
    return logging.getLogger(name)
