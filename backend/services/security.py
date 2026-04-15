"""
security.py — Input sanitization and output injection detection.

Step 30.1 — Prompt injection defense.
"""
import logging
import re

logger = logging.getLogger("deckr.security")

# ---------------------------------------------------------------------------
# Injection pattern lists
# ---------------------------------------------------------------------------

# Patterns in user-supplied messages that suggest prompt-injection attempts.
_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above|your)\s+(instructions?|prompts?|rules?|system)", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?(previous|prior|above|your)\s+(instructions?|prompts?|rules?)", re.IGNORECASE),
    re.compile(r"forget\s+(everything|all)\s+(you\s+)?(were\s+)?(told|instructed|given)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(a|an|the)\s+\w+", re.IGNORECASE),
    re.compile(r"new\s+instructions?\s*:", re.IGNORECASE),
    re.compile(r"act\s+as\s+(a|an|the)\s+\w+", re.IGNORECASE),
    re.compile(r"pretend\s+(you\s+are|to\s+be)\s+(a|an|the)\s+\w+", re.IGNORECASE),
    re.compile(r"reveal\s+(your\s+)?(system\s+prompt|instructions?|training|rules?)", re.IGNORECASE),
    re.compile(r"(print|repeat|output|echo|show|display)\s+(the\s+)?(above|previous|system|your)\s+(instructions?|prompt)", re.IGNORECASE),
    re.compile(r"\bjailbreak\b", re.IGNORECASE),
    re.compile(r"\bDAN\s+mode\b", re.IGNORECASE),
    re.compile(r"override\s+(safety|content|system)\s+(filter|check|guard|policy)", re.IGNORECASE),
]

# Patterns in agent output that suggest the model was manipulated into
# reproducing instruction-like syntax from its system prompt.
_OUTPUT_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"STEP\s+\d+\s+[—\-]\s+[A-Z]{3,}", re.IGNORECASE),   # "STEP 0 — READ"
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"(TOOL USE|REQUIRED STEPS?|CORE PRINCIPLES?)\s*[—:\-]", re.IGNORECASE),
    re.compile(r"you are (the|a|an) \w+ agent for Deckr", re.IGNORECASE),
    re.compile(r"<\|im_start\|>|<\|im_end\|>|<\|system\|>", re.IGNORECASE),  # raw special tokens
]

# Generous limit — long credit analysis prompts are legitimate.
_MAX_MESSAGE_LENGTH = 8_000


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def sanitize_message(message: str, source: str = "unknown") -> str:
    """
    Sanitize a user-supplied message before passing it to Orchestrate.

    Actions taken:
    - Truncates messages exceeding _MAX_MESSAGE_LENGTH.
    - Detects prompt-injection patterns and logs a WARNING.
    - Does NOT silently drop or blank the message — legitimate analyst
      messages that happen to trigger a pattern are preserved and logged
      so security team can review without blocking the workflow.

    Args:
        message: Raw user message string.
        source:  Identifier for log context (e.g., agent name or endpoint).

    Returns:
        Sanitized (possibly truncated) message string.
    """
    if not message:
        return message

    # Enforce max length
    if len(message) > _MAX_MESSAGE_LENGTH:
        logger.warning(
            "security: message truncated (%d → %d chars) source=%s",
            len(message), _MAX_MESSAGE_LENGTH, source,
        )
        message = message[:_MAX_MESSAGE_LENGTH] + "\n[MESSAGE TRUNCATED — maximum length exceeded]"

    # Detect injection patterns — log WARNING, do not block
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(message):
            logger.warning(
                "security: potential prompt injection detected "
                "(source=%s pattern=%r preview=%r)",
                source,
                pattern.pattern[:60],
                message[:120],
            )
            break   # one warning per message is enough

    return message


def detect_output_injection(reply: str, agent_name: str) -> None:
    """
    Scan an agent reply for signs the model was manipulated into echoing
    instruction-like syntax from its own system prompt.

    Logs a WARNING if a suspicious pattern is found; does not modify the reply.

    Args:
        reply:      The agent's raw response string.
        agent_name: Agent identifier for log context.
    """
    if not reply:
        return
    for pattern in _OUTPUT_INJECTION_PATTERNS:
        if pattern.search(reply):
            logger.warning(
                "security: instruction-like syntax in agent reply "
                "(agent=%s pattern=%r preview=%r)",
                agent_name,
                pattern.pattern[:60],
                reply[:200],
            )
            break
