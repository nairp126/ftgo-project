"""
Prompt Safety Scrubber Service.
Analyzes incoming ChatRequest payloads to detect prompt injection attempts,
jailbreaks, or unauthorized system prompt manipulations.
"""

from typing import List, Tuple
import re
from app.schemas.chat import ChatRequest
from app.core.logging import get_logger

logger = get_logger(__name__)


class SecurityPolicyViolation(Exception):
    """Raised when a prompt violates the safety guardrails."""
    def __init__(self, message: str, matched_pattern: str):
        super().__init__(message)
        self.matched_pattern = matched_pattern


class PromptSafetyScrubber:
    """
    A heuristic-based prompt scanner.
    Future iterations can be backed by LLM-based scanners or APIs like Lakera Guard.
    """
    
    # Highly indicative phrases common in jailbreaks or injections
    BLOCKLIST = [
        "ignore previous instructions",
        "disregard all prior instructions",
        "system prompt",
        "you are no longer an ai",
        "act as a developer", # DAN variations
        "do anything now",
        "developer mode enabled",
    ]

    @staticmethod
    def analyze_request(request: ChatRequest) -> Tuple[bool, str]:
        """
        Scans all messages in the payload.
        Returns (True, None) if safe.
        Returns (False, matched_pattern) if an injection is suspected.
        """
        for message in request.messages:
            raw_content = message.content.lower().strip()
            
            # Normalize: remove non-alphanumeric and collapse whitespace
            normalized_content = re.sub(r'[^a-z0-9\s]', '', raw_content)
            normalized_content = re.sub(r'\s+', ' ', normalized_content).strip()
            
            for pattern in PromptSafetyScrubber.BLOCKLIST:
                normalized_pattern = re.sub(r'[^a-z0-9\s]', '', pattern.lower())
                normalized_pattern = re.sub(r'\s+', ' ', normalized_pattern).strip()
                
                if normalized_pattern in normalized_content:
                    logger.warning(
                        f"Prompt injection detected! Matched pattern: '{pattern}' in message: '{raw_content[:50]}...'"
                    )
                    return False, pattern
                    
        return True, ""

    @staticmethod
    def verify_safety(request: ChatRequest) -> bool:
        """
        Raises SecurityPolicyViolation if the payload is malicious.
        """
        is_safe, pattern = PromptSafetyScrubber.analyze_request(request)
        if not is_safe:
            raise SecurityPolicyViolation(
                "Request blocked by safety policy. Potential prompt injection detected.",
                matched_pattern=pattern
            )
        return True
