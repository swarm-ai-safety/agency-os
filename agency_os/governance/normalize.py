"""Unicode normalization for adversarial input defense.

Pre-processes text before regex matching to defeat character-level evasion
techniques: zero-width character injection, Unicode homoglyphs, combining
marks / diacritical abuse, and leetspeak substitution.

This module is intentionally dependency-free (stdlib only).

ZERA-366
"""

from __future__ import annotations

import re
import unicodedata

# ---------------------------------------------------------------------------
# 1. Zero-width character stripping
# ---------------------------------------------------------------------------

# Zero-width space, non-joiner, joiner, word joiner, FEFF BOM
_ZERO_WIDTH_RE = re.compile("[\u200b\u200c\u200d\u2060\ufeff]")


def _strip_zero_width(text: str) -> str:
    """Remove zero-width Unicode characters that break word boundaries."""
    return _ZERO_WIDTH_RE.sub("", text)


# ---------------------------------------------------------------------------
# 2. Homoglyph transliteration (confusable characters -> ASCII Latin)
# ---------------------------------------------------------------------------

# Map of visually confusable characters to their Latin equivalents.
# Covers Cyrillic, Armenian, and other scripts commonly used in homoglyph
# attacks. Ordered by frequency of use in adversarial inputs.
_HOMOGLYPH_TABLE: dict[str, str] = {
    # Cyrillic -> Latin
    "\u0430": "a",  # а
    "\u0441": "c",  # с
    "\u0435": "e",  # е
    "\u043e": "o",  # о
    "\u0440": "p",  # р
    "\u0445": "x",  # х
    "\u0443": "y",  # у
    "\u0456": "i",  # і
    "\u0455": "s",  # ѕ
    "\u0501": "d",  # ԁ
    "\u04bb": "h",  # һ
    "\u043d": "h",  # н (sometimes used for h)
    "\u0432": "b",  # в (sometimes used for b)
    "\u043a": "k",  # к
    "\u043c": "m",  # м
    "\u0442": "t",  # т
    # Armenian -> Latin
    "\u0578": "n",  # ո
    "\u0575": "y",  # յ
    "\u0570": "h",  # հ
    # Greek -> Latin
    "\u03b1": "a",  # α
    "\u03bf": "o",  # ο
    "\u03b5": "e",  # ε
    "\u03b9": "i",  # ι
    "\u03ba": "k",  # κ
    "\u03c1": "p",  # ρ (rho, visually like p)
    "\u03c5": "u",  # υ
    "\u03bd": "v",  # ν
    # Fullwidth Latin -> ASCII Latin (CJK fullwidth forms)
    **{chr(c): chr(c - 0xFEE0) for c in range(0xFF21, 0xFF3B)},  # A-Z
    **{chr(c): chr(c - 0xFEE0) for c in range(0xFF41, 0xFF5B)},  # a-z
}

# Build a single-pass translation table for str.translate()
_HOMOGLYPH_TRANS = str.maketrans(_HOMOGLYPH_TABLE)


def _transliterate_homoglyphs(text: str) -> str:
    """Replace visually confusable Unicode characters with ASCII Latin."""
    return text.translate(_HOMOGLYPH_TRANS)


# ---------------------------------------------------------------------------
# 3. NFKD normalization (decomposes combining marks)
# ---------------------------------------------------------------------------


def _nfkd_normalize(text: str) -> str:
    """NFKD-normalize and strip combining marks (diacritics).

    NFKD decomposes characters like e\u0301 into base 'e' + combining accent,
    then we strip the combining category (Mn = Mark, Nonspacing).
    """
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


# ---------------------------------------------------------------------------
# 4. Leetspeak reversal
# ---------------------------------------------------------------------------

# Common leetspeak digit->letter mappings (reversed from attacker's perspective)
_LEET_REVERSE: dict[str, str] = {
    "0": "o",
    "1": "i",  # also "l", but "i" is more common in injection keywords
    "3": "e",
    "4": "a",
    "5": "s",
    "7": "t",
    "9": "g",
    "@": "a",
    "$": "s",
}

_LEET_TRANS = str.maketrans(_LEET_REVERSE)


def _reverse_leetspeak(text: str) -> str:
    """Reverse common leetspeak substitutions back to Latin letters."""
    return text.translate(_LEET_TRANS)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def normalize_for_matching(text: str) -> str:
    """Apply all normalization layers to prepare text for regex matching.

    Order matters:
    1. Strip zero-width chars first (they break every other step).
    2. NFKD normalize (decomposes combining marks into base + mark, then strip marks).
    3. Transliterate homoglyphs (Cyrillic/Greek/Armenian/fullwidth -> ASCII).
    4. Reverse leetspeak (digit substitutions back to letters).

    The original text is preserved elsewhere for display; this normalized
    form is only used for pattern matching / classification.

    Args:
        text: Raw input string, possibly containing adversarial characters.

    Returns:
        Normalized string suitable for regex matching.
    """
    result = _strip_zero_width(text)
    result = _nfkd_normalize(result)
    result = _transliterate_homoglyphs(result)
    result = _reverse_leetspeak(result)
    return result
