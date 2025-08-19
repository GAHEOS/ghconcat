"""
core.git – Git-related Protocols & default factory for ghconcat.

This module centralizes the Git contracts under the `ghconcat.core` namespace.
It re-exports the canonical Protocols from `core.interfaces.git` and the
default factory implementation from the discovery module.
"""

from ghconcat.core.interfaces.git import (
    GitRepositoryManagerProtocol,
    GitManagerFactoryProtocol,
)
from ghconcat.discovery.git_manager import DefaultGitManagerFactory

__all__ = [
    "GitRepositoryManagerProtocol",
    "GitManagerFactoryProtocol",
    "DefaultGitManagerFactory",
]