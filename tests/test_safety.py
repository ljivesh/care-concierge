"""The safety gate on its own: verdicts pass through, and every kind of failure fails closed.

The model is never called here. `safety.ask_model` (the one function that talks
to the model) is replaced, which is also how the classifier is made to raise
or time out. The graph tests then check that no tool runs after a failure.
"""

import asyncio
import logging

import pytest
from pydantic import ValidationError

from app import replies, safety
from app.contract import SafetyVerdict
from app.replies import Language
from app.safety import SafetyDecision, classify

LLM = object()  # never used: ask_model is replaced in every test


def model_says(monkeypatch, verdict: SafetyVerdict, language: Language) -> None:
    async def fake(llm, message):
        return SafetyDecision(verdict=verdict, language=language)

    monkeypatch.setattr(safety, "ask_model", fake)


def failures_logged(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith("safety_classifier_failed")]


# ---------- the classifier answers ----------


@pytest.mark.parametrize("verdict", list(SafetyVerdict))
async def test_verdict_and_language_pass_through(monkeypatch, verdict):
    model_says(monkeypatch, verdict, Language.HINGLISH)

    outcome = await classify(LLM, "seene mein dard", timeout_s=1, fallback_language=Language.EN)

    assert outcome.verdict == verdict
    assert outcome.language == Language.HINGLISH
    assert outcome.failed is False


# ---------- the classifier fails: fail closed ----------


async def test_classifier_raises_fails_closed_and_is_logged(monkeypatch, caplog):
    async def provider_down(llm, message):
        raise ConnectionError("provider unreachable")

    monkeypatch.setattr(safety, "ask_model", provider_down)

    with caplog.at_level(logging.ERROR, logger="concierge.safety"):
        outcome = await classify(LLM, "book cardiology", timeout_s=1, fallback_language=Language.HI)

    assert outcome.failed is True
    assert outcome.verdict is None  # in particular: NOT treated as SAFE
    assert outcome.language == Language.HI
    assert failures_logged(caplog) == ["safety_classifier_failed kind=error error=ConnectionError"]


async def test_classifier_times_out_fails_closed_and_is_logged(monkeypatch, caplog):
    async def hangs(llm, message):
        await asyncio.sleep(30)

    monkeypatch.setattr(safety, "ask_model", hangs)

    with caplog.at_level(logging.ERROR, logger="concierge.safety"):
        outcome = await asyncio.wait_for(
            classify(LLM, "my father collapsed", timeout_s=0.1, fallback_language=Language.EN),
            timeout=2,  # the test itself fails if classify does not stop at its own timeout
        )

    assert outcome.failed is True
    assert failures_logged(caplog) == ["safety_classifier_failed kind=timeout timeout_s=0.1"]


async def test_unreadable_model_answer_fails_closed(monkeypatch, caplog):
    async def returns_garbage(llm, message):
        return SafetyDecision.model_validate({"verdict": "PROBABLY_FINE", "language": "en"})

    monkeypatch.setattr(safety, "ask_model", returns_garbage)

    with caplog.at_level(logging.ERROR, logger="concierge.safety"):
        outcome = await classify(LLM, "hello", timeout_s=1, fallback_language=Language.EN)

    assert outcome.failed is True
    assert failures_logged(caplog) == [f"safety_classifier_failed kind=error error={ValidationError.__name__}"]


def test_verdict_outside_the_contract_cannot_be_built():
    with pytest.raises(ValidationError):
        SafetyDecision(verdict="MAYBE", language="en")


# ---------- the fixed replies ----------


def test_language_fallback_when_the_classifier_cannot_tell_us():
    assert replies.guess_language("रविवार को कब खुलता है?", "en") == Language.HI
    assert replies.guess_language("sunday ko kab khulta hai", "hinglish") == Language.HINGLISH
    assert replies.guess_language("when does it open", "en") == Language.EN


@pytest.mark.parametrize("language", list(Language))
def test_fail_closed_reply_always_gives_the_emergency_number(language):
    text = replies.safety_unavailable(language)

    assert "112" in text
    assert "wellness room" in text or "वेलनेस रूम" in text


@pytest.mark.parametrize("language", list(Language))
def test_emergency_reply_has_112_and_the_societys_hospital_number(language):
    text = replies.emergency(language, hospital="Arogya Multispeciality Hospital", phone="+91 120 4555 2200", minutes=5)

    assert "112" in text and "+91 120 4555 2200" in text and "Arogya" in text
    assert "112" in replies.emergency_not_recorded(language)


def test_hindi_replies_are_in_hindi_script():
    for text in (
        replies.safety_unavailable(Language.HI),
        replies.medical_advice(Language.HI),
        replies.emergency_not_recorded(Language.HI),
    ):
        assert replies.DEVANAGARI.search(text)
    assert not replies.DEVANAGARI.search(replies.medical_advice(Language.HINGLISH))
