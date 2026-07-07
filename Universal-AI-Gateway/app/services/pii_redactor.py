"""
PII detection and redaction service.
Detects and masks emails, SSNs, credit card numbers, and phone numbers.
Supports Requirements 6.4, 13.4.
"""

import re
from typing import List, Tuple

# Pattern name → compiled regex
PII_PATTERNS: List[Tuple[str, re.Pattern]] = [
    # Email addresses
    ("email", re.compile(
        r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    )),
    # US Social Security Numbers (XXX-XX-XXXX)
    ("ssn", re.compile(
        r"\b\d{3}-\d{2}-\d{4}\b",
    )),
    # Credit card numbers (13-19 digits, optionally separated by spaces/dashes)
    ("credit_card", re.compile(
        r"\b(?:\d[ \-]*?){13,19}\b",
    )),
    # US/international phone numbers
    ("phone", re.compile(
        r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
    )),
]

REDACTED = "[REDACTED]"


def detect_pii(text: str) -> List[dict]:
    """
    Scan *text* for PII patterns.

    Returns:
        List of dicts with ``type``, ``start``, ``end`` for each match.
    """
    findings = []
    for pii_type, pattern in PII_PATTERNS:
        for match in pattern.finditer(text):
            findings.append({
                "type": pii_type,
                "start": match.start(),
                "end": match.end(),
            })
    return findings


def redact_pii(text: str) -> str:
    """
    Replace all detected PII in *text* with ``[REDACTED]``.

    Processes replacements from right-to-left so that string
    indices remain valid after each substitution.
    """
    findings = detect_pii(text)
    if not findings:
        return text

    # Sort by start position descending so we replace from the end
    findings.sort(key=lambda f: f["start"], reverse=True)
    result = text
    for finding in findings:
        result = result[:finding["start"]] + REDACTED + result[finding["end"]:]
    return result


def contains_pii(text: str) -> bool:
    """Quick check: does the text contain any PII?"""
    return len(detect_pii(text)) > 0
