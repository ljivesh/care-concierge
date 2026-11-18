"""The one place a chat model is created.

Every supported provider speaks the OpenAI chat-completions protocol, so one
client class covers them all. Switching provider is an env change:
LLM_PROVIDER picks a known base URL, or LLM_BASE_URL sets any other endpoint.
"""

from langchain_openai import ChatOpenAI

from app.config import Settings

PROVIDER_BASE_URLS = {
    "groq": "https://api.groq.com/openai/v1",
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
}


def make_llm(settings: Settings) -> ChatOpenAI:
    base_url = settings.llm_base_url or PROVIDER_BASE_URLS.get(settings.llm_provider.lower())
    if not base_url:
        raise ValueError(
            f"Unknown LLM_PROVIDER '{settings.llm_provider}'. Use one of "
            f"{sorted(PROVIDER_BASE_URLS)}, or set LLM_BASE_URL to an OpenAI-compatible endpoint."
        )
    return ChatOpenAI(
        model=settings.llm_model,
        # With no key the app still starts; every model call then fails, and the
        # safety gate handles that failure like any other (see app/safety.py).
        api_key=settings.llm_api_key or "not-set",
        base_url=base_url,
        temperature=0,
        timeout=settings.llm_timeout_s,  # every LLM call has a timeout
        max_retries=2,  # the client waits and retries when the provider rate-limits (HTTP 429)
    )
