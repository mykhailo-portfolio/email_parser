# src/app/utils/transform.py
"""
Text normalization utilities for consistent, Unicode-safe processing.

Used across all pipeline stages (Gmail ingestion, company matching,
and phrase classification). Normalization here must preserve human
readability and allow reliable exact-phrase matching.
"""

from __future__ import annotations
import re

__all__ = ["normalize_soft", "normalize_company"]

# ---------------------------------------------------------------------
# Safe replacements for common punctuation variants and symbols.
# Applied before regex-based normalization.
# ---------------------------------------------------------------------
_NORMALIZE_MAP = {
    "&": " and ",
    "’": "'",
    "‘": "'",
    "“": '"',
    "”": '"',
    "–": "-",   # en-dash → hyphen
    "—": "-",   # em-dash → hyphen
}


def normalize_soft(s: str) -> str:
    """
    Perform gentle, Unicode-aware normalization of free text.

    - Converts to lowercase using `.casefold()` (locale-independent)
    - Applies safe replacements defined in `_NORMALIZE_MAP`
    - Replaces punctuation and separators with spaces but preserves
      letters (of any language) and digits
    - Collapses repeated whitespace into one
    - Keeps text readable for exact substring matching
    """
    if not s:
        return ""

    # Lowercase conversion (handles Unicode consistently)
    s = s.casefold()

    # Apply safe symbol replacements (&, curly quotes, dashes, etc.)
    for k, v in _NORMALIZE_MAP.items():
        s = s.replace(k, v)

    # Replace any punctuation/separator (category P or Z) with a space.
    # This keeps all word and number characters (Unicode aware).
    s = re.sub(r"[^\w]+", " ", s, flags=re.UNICODE)

    # Collapse multiple spaces and trim edges
    s = re.sub(r"\s+", " ", s).strip()

    return s


# ---------------------------------------------------------------------
# Regex of common legal suffixes to strip from company names.
# Keeps comparison consistent for variants like "Inc.", "LLC", "GmbH".
# ---------------------------------------------------------------------
_LEGAL_SUFFIX = r"(inc\.?|ltd\.?|gmbh|s\.?a\.?s\.?|s\.?r\.?l\.?|llc|corp\.?|co\.?|plc)"


def normalize_company(s: str) -> str:
    """
    Normalize a company name for reliable comparison.

    - Applies `normalize_soft()` for base cleanup
    - Removes legal suffixes (Inc., Ltd., GmbH, etc.)
    - Collapses residual whitespace
    - Optionally can enforce ≥2 tokens rule (to avoid single-word noise)
    """
    s = normalize_soft(s)
    if not s:
        return ""

    # Remove legal suffixes (with optional dots)
    s = re.sub(rf"\b{_LEGAL_SUFFIX}\b\.?", "", s)

    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()

    return s
