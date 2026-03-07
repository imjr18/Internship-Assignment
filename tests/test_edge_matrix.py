"""
Large deterministic edge-case matrix for parser and guardrail reliability.

This file intentionally contains hundreds of parametrized cases to stress:
- party-size extraction
- modification-detail detection
- function-text sanitization
- datetime formatting helpers
"""

from __future__ import annotations

from datetime import datetime

import pytest

from agent.orchestrator import AgentOrchestrator


_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}


def _party_positive_cases() -> list[tuple[str, int]]:
    cases: list[tuple[str, int]] = []
    for n in range(1, 25):
        cases.append((f"table for {n} people", n))
        cases.append((f"party of {n}", n))
        cases.append((f"we are {n}", n))
        cases.append((f"{n}", n))
        cases.append((f"{n} including me", n))
        if n <= 12:
            words = [
                "one", "two", "three", "four", "five", "six",
                "seven", "eight", "nine", "ten", "eleven", "twelve",
            ]
            w = words[n - 1]
            cases.append((w, n))
            cases.append((f"{w} including me", n))
        if n <= 23:
            cases.append((f"with {n} of my friends", n + 1))
        if n <= 11:
            words = [
                "one", "two", "three", "four", "five", "six",
                "seven", "eight", "nine", "ten", "eleven",
            ]
            w = words[n - 1]
            cases.append((f"with {w} friends", n + 1))
            cases.append((f"me and {n} friends", n + 1))
            cases.append((f"me and {w} friends", n + 1))
    return cases


def _party_negative_cases() -> list[str]:
    static = [
        "table for zero people",
        "party of zero",
        "we are zero",
        "just me maybe",
        "for many people",
        "a big party",
        "party soon",
        "table please",
        "two tables maybe",
        "2 seats and 1 child",
        "with friends tonight",
    ]
    generated = [f"book it option {c}" for c in "abcdefghijklmnopqrst"]
    return static + generated


def _modify_positive_cases() -> list[str]:
    cases: list[str] = []
    for hour in range(1, 13):
        cases.append(f"change it to {hour} pm")
    for party in range(1, 25):
        cases.append(f"make it for {party} people")
    for day in range(1, 15):
        cases.append(f"move it to 2026-03-{day:02d}")
    return cases


def _modify_negative_cases() -> list[str]:
    static = [
        "can i modify it",
        "can i change it",
        "modify reservation",
        "update booking",
        "change time",
        "change date",
        "update details",
        "please change it",
        "edit this booking",
        "i made a mistake",
    ]
    generated = [f"modify this request token {i}" for i in range(1, 21)]
    return static + generated


def _sanitize_cases() -> list[tuple[str, str]]:
    cases: list[tuple[str, str]] = []
    cases.extend(
        [
            ("I'll check that <function", "I'll check that"),
            ("<function=search_restaurants>{\"q\":\"x\"}</function>", ""),
            ("prefix </function>search>{}</function> suffix", "prefix  suffix"),
            ("normal sentence", "normal sentence"),
            ("<fun", ""),
        ]
    )
    for i in range(1, 11):
        cases.append((f"Text {i} <function", f"Text {i}"))
    for i in range(1, 6):
        cases.append((f"<function=check>{i}</function>", ""))
    for i in range(1, 6):
        cases.append((f"alpha {i} </function>beta>{i}</function>", f"alpha {i} "))
    return cases


def _valid_datetime_inputs() -> list[str]:
    cases: list[str] = []
    for month in range(1, 7):
        for hour in (0, 7, 12):
            cases.append(f"2026-{month:02d}-15T{hour:02d}:30:00")
    return cases


def _invalid_datetime_inputs() -> list[str]:
    return [
        "",
        "not-a-date",
        "2026-13-01T10:00:00",
        "2026-00-10T10:00:00",
        "2026-03-32T10:00:00",
        "2026-03-10T25:00:00",
        "2026/03/10 10:00",
        "15-03-2026 19:00",
        "tomorrow evening",
        "2026-03-1x",
        "07:30 PM",
        "null",
    ]


def _valid_slot_inputs() -> list[str]:
    cases: list[str] = []
    for day in range(1, 7):
        for hour in (9, 13):
            cases.append(f"2026-04-{day:02d}T{hour:02d}:00:00")
    return cases


def _invalid_slot_inputs() -> list[str]:
    return [
        "",
        "abc",
        "2026-04-00T19:00:00",
        "2026-04-32T19:00:00",
        "2026-04-12 19:00",
        "19:00",
        "next friday",
        "2026/04/12",
    ]


PARTY_POSITIVE_CASES = _party_positive_cases()  # 72
PARTY_NEGATIVE_CASES = _party_negative_cases()  # 30
MODIFY_POSITIVE_CASES = _modify_positive_cases()  # 50
MODIFY_NEGATIVE_CASES = _modify_negative_cases()  # 30
SANITIZE_CASES = _sanitize_cases()  # 25
VALID_DATETIME_INPUTS = _valid_datetime_inputs()  # 18
INVALID_DATETIME_INPUTS = _invalid_datetime_inputs()  # 12
VALID_SLOT_INPUTS = _valid_slot_inputs()  # 12
INVALID_SLOT_INPUTS = _invalid_slot_inputs()  # 8


@pytest.mark.parametrize("text,expected", PARTY_POSITIVE_CASES)
def test_party_size_extraction_positive_matrix(text: str, expected: int):
    assert AgentOrchestrator._extract_party_size_from_text(text) == expected


@pytest.mark.parametrize("text", PARTY_NEGATIVE_CASES)
def test_party_size_extraction_negative_matrix(text: str):
    assert AgentOrchestrator._extract_party_size_from_text(text) is None


@pytest.mark.parametrize("text", MODIFY_POSITIVE_CASES)
def test_modification_detector_positive_matrix(text: str):
    orchestrator = AgentOrchestrator.__new__(AgentOrchestrator)
    assert orchestrator._has_explicit_modification_details(text) is True


@pytest.mark.parametrize("text", MODIFY_NEGATIVE_CASES)
def test_modification_detector_negative_matrix(text: str):
    orchestrator = AgentOrchestrator.__new__(AgentOrchestrator)
    assert orchestrator._has_explicit_modification_details(text) is False


@pytest.mark.parametrize("raw,expected", SANITIZE_CASES)
def test_sanitize_function_text_matrix(raw: str, expected: str):
    assert AgentOrchestrator._sanitize_assistant_text(raw) == expected.strip()


@pytest.mark.parametrize("raw", VALID_DATETIME_INPUTS)
def test_reservation_datetime_formatting_valid_matrix(raw: str):
    date_str, time_str = AgentOrchestrator._reservation_datetime_to_booking_fields(raw)
    dt = datetime.fromisoformat(raw)
    expected_date = dt.strftime("%a, %b %d")
    expected_time = f"{dt.strftime('%I').lstrip('0') or '12'}:{dt.strftime('%M %p')}"
    assert date_str == expected_date
    assert time_str == expected_time


@pytest.mark.parametrize("raw", INVALID_DATETIME_INPUTS)
def test_reservation_datetime_formatting_invalid_matrix(raw: str):
    date_str, time_str = AgentOrchestrator._reservation_datetime_to_booking_fields(raw)
    assert date_str is None
    assert time_str is None


@pytest.mark.parametrize("raw", VALID_SLOT_INPUTS)
def test_slot_datetime_formatting_valid_matrix(raw: str):
    formatted = AgentOrchestrator._format_slot_datetime(raw)
    dt = datetime.fromisoformat(raw)
    expected = f"{dt.strftime('%a, %b %d')} at {(dt.strftime('%I').lstrip('0') or '12')}:{dt.strftime('%M %p')}"
    assert formatted == expected


@pytest.mark.parametrize("raw", INVALID_SLOT_INPUTS)
def test_slot_datetime_formatting_invalid_matrix(raw: str):
    formatted = AgentOrchestrator._format_slot_datetime(raw)
    if not raw:
        assert formatted == "an available time"
    else:
        assert isinstance(formatted, str)
