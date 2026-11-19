"""The eval's own machinery: the numbers it prints, and replay without an API key."""

import json

import pytest

from app import safety
from app.contract import SafetyVerdict
from app.graph import respond, router, verify
from app.replies import Language
from app.safety import SafetyDecision
from evals.cache import CacheMiss, ModelCache
from evals.metrics import accuracy, per_class


def test_precision_and_recall():
    pairs = [("EMERGENCY", "EMERGENCY"), ("EMERGENCY", "SAFE"), ("SAFE", "SAFE"), ("SAFE", "SAFE")]

    rows = {row["class"]: row for row in per_class(pairs, ["EMERGENCY", "SAFE"])}

    assert rows["EMERGENCY"]["precision"] == 1.0  # everything we called an emergency was one
    assert rows["EMERGENCY"]["recall"] == 0.5  # but we found only one of the two
    assert rows["SAFE"]["precision"] == pytest.approx(2 / 3)
    assert accuracy(pairs) == 0.75


@pytest.fixture
def restore_model_calls():
    originals = (safety.ask_model, router.ask_model, respond.ask_model, verify.ask_model)
    yield
    safety.ask_model, router.ask_model, respond.ask_model, verify.ask_model = originals


async def test_recorded_output_is_replayed_without_calling_the_model(tmp_path, restore_model_calls):
    path = tmp_path / "outputs.json"
    calls = []

    async def real_model(llm, message, previous=None):
        calls.append(message)
        return SafetyDecision(verdict=SafetyVerdict.EMERGENCY, language=Language.EN)

    safety.ask_model = real_model
    recording = ModelCache(model="test-model", live=True, record=False, path=path)
    recording.install()
    await safety.ask_model(None, "he collapsed")
    recording.save()
    assert calls == ["he collapsed"] and json.loads(path.read_text())["model"] == "test-model"

    # A second run with no API key: same answer, and the model is not called again.
    safety.ask_model = real_model
    replaying = ModelCache(model="test-model", live=False, record=False, path=path)
    replaying.install()
    decision = await safety.ask_model(None, "he collapsed")

    assert decision.verdict == SafetyVerdict.EMERGENCY
    assert calls == ["he collapsed"]
    assert (replaying.hits, replaying.live_calls, replaying.misses) == (1, 0, [])


async def test_unrecorded_message_without_a_key_is_a_counted_miss(tmp_path, restore_model_calls):
    cache = ModelCache(model="test-model", live=False, record=False, path=tmp_path / "empty.json")
    cache.install()

    with pytest.raises(CacheMiss):
        await safety.ask_model(None, "a message nobody recorded")

    assert len(cache.misses) == 1
