"""
core.git – Git-related Protocols & default factory for ghconcat.

This module centralizes the Git contracts under the `ghconcat.core` namespace
while preserving the exact runtime classes by re-using the canonical
definitions from the original module. This avoids duplication and guarantees
test compatibility (type identity remains the same).
"""

from __future__ import annotations

from ghconcat.discovery.git_manager import (  # reuse canonical definitions
    GitRepositoryManagerProtocol,
    GitManagerFactoryProtocol,
    DefaultGitManagerFactory,
)

__all__ = [
    "GitRepositoryManagerProtocol",
    "GitManagerFactoryProtocol",
    "DefaultGitManagerFactory",
]