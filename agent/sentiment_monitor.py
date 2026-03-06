"""
Module: agent/sentiment_monitor.py

Monitors user messages for negative sentiment, hostility, distress,
or out-of-scope requests that should trigger escalation.

Uses keyword/pattern matching (no external model dependency).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class SentimentResult:
    """Result of sentiment analysis on a single message."""

    should_escalate: bool
    urgency_level: str  # "low" | "medium" | "high"
    reason: str
    score: float  # -1.0 (hostile) to 1.0 (positive)


# Patterns sorted by urgency
_HIGH_URGENCY_PATTERNS = [
    r"\b(threat|threaten|kill|die|hurt|harm|dangerous|weapon)",
    r"\b(sue|lawyer|attorney|legal action|lawsuit)",
    r"\b(fuck|shit|damn|ass|bitch|bastard)",
]

_MEDIUM_URGENCY_PATTERNS = [
    r"\b(angry|furious|outraged|disgusted|horrible)\b",
    r"\b(worst|terrible|unacceptable|ridiculous|scam)\b",
    r"\b(complaint|complain|refund|compensation|manager)\b",
    r"\b(never coming back|never again|lost my business)\b",
]

_LOW_URGENCY_PATTERNS = [
    r"\b(frustrated|annoyed|disappointed|unhappy|upset)\b",
    r"\b(long wait|slow|poor service|rude)\b",
]

_ESCALATION_REQUEST_PATTERNS = [
    r"\b(speak to|talk to|get me).{0,20}(human|person|manager|supervisor|real)\b",
    r"\b(human agent|real person|actual person)\b",
    r"\b(not (a )?bot|stop being (a )?bot)\b",
]

_OUT_OF_SCOPE_PATTERNS = [
    r"\b(wedding|event planning|catering|private event)\b",
    r"\b(food poisoning|allergic reaction|medical)\b",
    r"\b(lost item|lost property|left something)\b",
    r"\bleft\b.{0,20}\b(at the restaurant|at the table|behind|there)\b",
]

_POSITIVE_PATTERNS = [
    r"\b(thank|thanks|great|wonderful|amazing|perfect|love)\b",
    r"\b(excellent|fantastic|brilliant|awesome)\b",
]


def analyze_sentiment(message: str, session_id: str = "") -> SentimentResult:
    """Analyze a user message for sentiment and escalation triggers.

    Returns a SentimentResult with escalation recommendation.
    """
    text = message.lower().strip()

    # Check explicit escalation requests first
    for pat in _ESCALATION_REQUEST_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            logger.info(
                "escalation_requested",
                session_id=session_id,
                pattern=pat,
            )
            return SentimentResult(
                should_escalate=True,
                urgency_level="medium",
                reason="Guest explicitly requested human agent",
                score=-0.3,
            )

    # High urgency
    for pat in _HIGH_URGENCY_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            logger.warning(
                "high_urgency_detected",
                session_id=session_id,
                pattern=pat,
            )
            return SentimentResult(
                should_escalate=True,
                urgency_level="high",
                reason="Hostile or threatening language detected",
                score=-0.9,
            )

    # Medium urgency
    medium_matches = sum(
        1 for pat in _MEDIUM_URGENCY_PATTERNS
        if re.search(pat, text, re.IGNORECASE)
    )
    if medium_matches >= 2:
        return SentimentResult(
            should_escalate=True,
            urgency_level="medium",
            reason="Multiple indicators of strong dissatisfaction",
            score=-0.6,
        )

    # Out of scope
    for pat in _OUT_OF_SCOPE_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return SentimentResult(
                should_escalate=True,
                urgency_level="low",
                reason="Request appears out of scope for reservation system",
                score=-0.2,
            )

    # Low urgency — flag but don't escalate automatically
    low_matches = sum(
        1 for pat in _LOW_URGENCY_PATTERNS
        if re.search(pat, text, re.IGNORECASE)
    )
    if low_matches >= 1:
        return SentimentResult(
            should_escalate=False,
            urgency_level="low",
            reason="Mild negative sentiment detected",
            score=-0.3,
        )

    # Positive
    pos_matches = sum(
        1 for pat in _POSITIVE_PATTERNS
        if re.search(pat, text, re.IGNORECASE)
    )
    if pos_matches >= 1:
        return SentimentResult(
            should_escalate=False,
            urgency_level="low",
            reason="Positive sentiment",
            score=0.7,
        )

    # Neutral
    return SentimentResult(
        should_escalate=False,
        urgency_level="low",
        reason="Neutral",
        score=0.0,
    )


def check_prompt_injection(message: str) -> bool:
    """Detect common prompt injection attempts.

    Returns True if the message looks like it contains an injection.
    """
    injection_patterns = [
        r"ignore\s+(all\s+)?(previous|above|prior)\s+(instructions|prompts|rules)",
        r"you\s+are\s+now",
        r"new\s+persona",
        r"system\s*prompt",
        r"^\s*#+\s*system\s+override\b",
        r"^\s*#+\s*new\s+instructions?\b",
        r"reveal\s+your\s+(instructions|prompt|rules)",
        r"pretend\s+(you\s+are|to\s+be)",
        r"act\s+as",
        r"jailbreak",
        r"DAN\b",
        r"do\s+anything\s+now",
    ]
    text = message.lower()
    for pat in injection_patterns:
        if re.search(pat, text, re.IGNORECASE):
            return True
    return False
