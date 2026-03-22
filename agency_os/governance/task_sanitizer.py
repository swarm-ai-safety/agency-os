"""Sanitize task descriptions to mitigate prompt injection attacks.

Applies defense-in-depth layers:
1. Strip known prompt-injection patterns (system prompt overrides, role-play
   directives, delimiter manipulation).
2. Enforce structural boundaries so the LLM clearly distinguishes user-supplied
   task text from system instructions.
3. Flag suspicious descriptions for audit logging.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Patterns that indicate prompt injection attempts
# ---------------------------------------------------------------------------

# Attempts to override system prompts or assume new roles
_SYSTEM_OVERRIDE_PATTERN = re.compile(
    r"(?:"
    r"(?:ignore|disregard|forget|override|bypass)\s+"
    r"(?:all\s+)?(?:previous|prior|above|earlier|system|original)\s+"
    r"(?:instructions?|prompts?|rules?|directives?|guidelines?|context)"
    r"|"
    r"(?:you\s+are\s+now|new\s+instructions?|system\s*:\s*)"
    r"|"
    r"<\s*/?(?:system|instruction|prompt|admin)\s*>"
    r"|"
    r"\[\s*(?:SYSTEM|INST|ADMIN)\b"
    r")",
    re.IGNORECASE,
)

# Attempts to use markdown/XML delimiters to inject fake boundaries
_DELIMITER_INJECTION_PATTERN = re.compile(
    r"(?:"
    r"```\s*(?:system|instruction|admin)"
    r"|"
    r"---+\s*(?:system|new\s+prompt|instructions?)"
    r"|"
    r"={3,}\s*(?:system|instructions?)"
    r")",
    re.IGNORECASE,
)

# Role-play / persona-switch attempts
_ROLE_SWITCH_PATTERN = re.compile(
    r"(?:"
    r"(?:act|behave|pretend|respond)\s+(?:as|like)\s+(?:a\s+)?(?:different|new|another)"
    r"|"
    r"(?:you\s+must|you\s+should|you\s+will)\s+(?:now\s+)?(?:act|be|become|pretend)"
    r"|"
    r"(?:switch|change)\s+(?:to\s+)?(?:your\s+)?(?:role|persona|identity|character)"
    r")",
    re.IGNORECASE,
)

_ALL_PATTERNS = [
    ("system_override", _SYSTEM_OVERRIDE_PATTERN),
    ("delimiter_injection", _DELIMITER_INJECTION_PATTERN),
    ("role_switch", _ROLE_SWITCH_PATTERN),
]


@dataclass(frozen=True)
class SanitizationResult:
    """Outcome of sanitizing a task description."""

    sanitized: str
    flagged: bool  # True if any injection patterns were detected
    flags: list[str]  # Which pattern categories matched


def sanitize_task_description(raw: str) -> SanitizationResult:
    """Sanitize a task description string.

    Strips known injection patterns and wraps the content in clear
    structural delimiters so downstream LLM calls can distinguish
    user-supplied text from system instructions.

    Args:
        raw: The raw task description from the API caller.

    Returns:
        SanitizationResult with the cleaned text and any flags.
    """
    flags: list[str] = []
    cleaned = raw

    for name, pattern in _ALL_PATTERNS:
        if pattern.search(cleaned):
            flags.append(name)
            cleaned = pattern.sub("[REDACTED]", cleaned)

    # Collapse any remaining XML-style tags that could confuse the model
    cleaned = re.sub(r"<\s*/?\s*\w+\s*>", "", cleaned)

    return SanitizationResult(
        sanitized=cleaned.strip(),
        flagged=bool(flags),
        flags=flags,
    )


def wrap_task_for_llm(sanitized_description: str) -> str:
    """Wrap a sanitized task description with structural delimiters.

    The delimiters make it unambiguous to the LLM that this is user-supplied
    task content, not system instructions.

    Args:
        sanitized_description: Already-sanitized task text.

    Returns:
        Wrapped string safe for inclusion in an LLM user prompt.
    """
    return f"[USER_TASK_BEGIN]\n{sanitized_description}\n[USER_TASK_END]"
