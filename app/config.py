"""All configuration comes from environment variables, read once here.

Nothing else in the app calls os.environ. To switch LLM provider or model,
change the LLM_* variables in .env; no code changes.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Field names map to env vars case-insensitively: database_url <- DATABASE_URL
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://concierge:concierge@localhost:5433/concierge"
    db_statement_timeout_ms: int = 5000
    tool_timeout_s: float = 10.0

    # Passages scoring below this cosine similarity are not used as evidence.
    retrieval_min_similarity: float = 0.36

    # Any OpenAI-compatible endpoint works. LLM_PROVIDER picks a known base URL
    # (groq, openai, openrouter); LLM_BASE_URL overrides it for anything else.
    llm_provider: str = "groq"
    llm_base_url: str = ""
    llm_api_key: str = ""  # empty is valid: `make eval` must run without a key
    llm_model: str = ""
    llm_timeout_s: float = 30.0
    # Total budget for the safety check, including one retry and any rate-limit
    # wait. Groq's free tier (8,000 tokens a minute) can make a call wait 7 seconds.
    safety_timeout_s: float = 20.0


@lru_cache
def get_settings() -> Settings:
    """Cached so the env is parsed once. A function (not a module-level
    object) so tests can override it."""
    return Settings()
