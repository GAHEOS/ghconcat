"""
ghconcat.utils – Small shared utilities (suffix normalization, filters).
"""
from .suffixes import normalize_suffixes, compute_suffix_filters, is_suffix_allowed

__all__ = ["normalize_suffixes", "compute_suffix_filters", "is_suffix_allowed"]