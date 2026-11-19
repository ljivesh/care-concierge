"""Record and replay of model outputs, so the eval runs with no API key.

The app talks to the model in exactly four places: safety.ask_model,
router.ask_model, respond.ask_model and verify.ask_model. `install` swaps each for a wrapper:

  - the answer is in the cache  -> return it; the model is not called
  - not in the cache, key set   -> call the model, store the answer
  - not in the cache, no key    -> raise CacheMiss (the eval reports it)

The cache is one JSON file, committed under evals/cache/. Entries are keyed by
a hash of what the model was asked, so an edited eval row is a cache miss and
never silently replays the answer to the old text.
"""

import hashlib
import json
from pathlib import Path

from langchain_core.messages import AIMessage, AnyMessage, SystemMessage

from app import safety
from app.graph import respond, router, verify
from app.graph.router import Route
from app.safety import SafetyDecision

CACHE_FILE = Path(__file__).parent / "cache" / "model_outputs.json"


class CacheMiss(RuntimeError):
    """A model output is needed, it was never recorded, and there is no API key."""


def _plain(messages: list[AnyMessage]) -> list[list[str]]:
    """Messages as [type, text] pairs. The system prompt is left out: it contains the
    current time, which would make every key different on every run."""
    return [[m.type, str(m.content)] for m in messages if not isinstance(m, SystemMessage)]


class ModelCache:
    def __init__(self, *, model: str, live: bool, record: bool, path: Path = CACHE_FILE) -> None:
        self.path = path
        self.live = live  # an API key is configured, so misses can be filled
        self.record = record  # ignore what is stored and ask the model again
        self.model = model
        self.hits = 0
        self.live_calls = 0
        self.misses: list[str] = []
        stored = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        self.recorded_with = stored.get("model", "nothing recorded yet")
        self.entries: dict[str, dict] = stored.get("entries", {})

    async def get(self, kind: str, asked: object, call, *, preview: str) -> dict:
        key = hashlib.sha256(json.dumps([kind, asked], ensure_ascii=False).encode()).hexdigest()[:24]
        if key in self.entries and not self.record:
            self.hits += 1
            return self.entries[key]["output"]
        if not self.live:
            self.misses.append(f"{kind}: {preview[:70]}")
            raise CacheMiss(f"no recorded {kind} output for: {preview[:70]}")
        output = await call()
        self.live_calls += 1
        self.entries[key] = {"kind": kind, "input": preview[:200], "output": output}
        return output

    def save(self) -> None:
        if self.live_calls == 0:
            return  # nothing new: leave the committed file byte-for-byte as it was
        self.path.parent.mkdir(parents=True, exist_ok=True)
        body = {"model": self.model, "entries": dict(sorted(self.entries.items()))}
        self.path.write_text(json.dumps(body, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    def install(self) -> None:
        """Put the cache in front of the four model calls."""
        real_safety, real_router, real_respond = safety.ask_model, router.ask_model, respond.ask_model
        real_verify = verify.ask_model

        async def cached_verify(llm, question, passages, answer):
            async def call():
                return (await real_verify(llm, question, passages, answer)).model_dump(mode="json")

            asked = [question, passages, answer]
            return verify.Grounding(**await self.get("verify", asked, call, preview=question))

        verify.ask_model = cached_verify

        async def cached_safety(llm, message, previous=None):
            async def call():
                return (await real_safety(llm, message, previous)).model_dump(mode="json")

            asked = [message, previous] if previous else message
            return SafetyDecision(**await self.get("safety", asked, call, preview=message))

        async def cached_router(llm, conversation):
            async def call():
                return (await real_router(llm, conversation)).model_dump(mode="json")

            asked = _plain(conversation)
            return Route(**await self.get("router", asked, call, preview=asked[-1][1]))

        async def cached_respond(llm, tools, messages):
            async def call():
                reply = await real_respond(llm, tools, messages)
                calls = [{"name": c["name"], "args": c["args"], "id": c["id"]} for c in reply.tool_calls]
                return {"content": str(reply.content), "tool_calls": calls}

            asked = [sorted(t.name for t in tools), _plain(messages)]
            preview = next((text for kind, text in asked[1] if kind == "human"), "")
            output = await self.get("respond", asked, call, preview=preview)
            return AIMessage(
                content=output["content"],
                tool_calls=[{**c, "type": "tool_call"} for c in output["tool_calls"]],
            )

        safety.ask_model, router.ask_model, respond.ask_model = cached_safety, cached_router, cached_respond
