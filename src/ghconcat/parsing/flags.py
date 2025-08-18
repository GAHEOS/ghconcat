"""
flags – Centralized CLI flag sets for ghconcat.

This module defines the canonical set of *value-taking* flags used across
the codebase. Having a single source of truth prevents subtle divergences
between the directive parser and the monolithic executor.

Exports
-------
VALUE_FLAGS : Set[str]
    Flags whose *next* token is considered a value (e.g., "-o FILE").
"""
from typing import Set


# Canonical set of flags that take a value in the next token.
VALUE_FLAGS: Set[str] = {
    "-w", "--workdir", "-W", "--workspace",
    "-a", "--add-path", "-A", "--exclude-path",
    "-g", "--git-path", "-G", "--git-exclude",
    "-f", "--url",
    "-F", "--url-scrape",
    "-d", "--url-scrape-depth",
    "-D", "--disable-same-domain",
    "-s", "--suffix", "-S", "--exclude-suffix",
    "-n", "--total-lines", "-N", "--start-line",
    "-t", "--template", "-o", "--output", "-T", "--child-template",
    "-u", "--wrap", "--ai-model", "--ai-system-prompt",
    "--ai-seeds", "--ai-temperature", "--ai-top-p",
    "--ai-presence-penalty", "--ai-frequency-penalty",
    "--ai-max-tokens", "--ai-reasoning-effort",
    "-e", "--env", "-E", "--global-env",
    "-y", "--replace", "-Y", "--preserve",
}