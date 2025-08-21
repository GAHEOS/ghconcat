from __future__ import annotations
from typing import Protocol, runtime_checkable


@runtime_checkable
class LoggerLikeProtocol(Protocol):
    """Minimal logging surface used across the project."""

    def debug(self, msg: str, *args, **kwargs) -> None: ...

    def info(self, msg: str, *args, **kwargs) -> None: ...

    def warning(self, msg: str, *args, **kwargs) -> None: ...

    def error(self, msg: str, *args, **kwargs) -> None: ...


@runtime_checkable
class LoggerFactoryProtocol(Protocol):
    """Factory for scoped loggers."""

    def get_logger(self, name: str) -> LoggerLikeProtocol:
        """Return a logger instance associated with `name`."""
        ...
