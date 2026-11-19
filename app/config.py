"""All configuration comes from environment variables, read once here.

Nothing else in the app calls os.environ. To switch LLM provider or model,
change the LLM_* variables in .env; no code changes.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Field names map to env vars case-insensitively: database_url <- DATABASE_URL
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Where the built React app lives (the Dockerfile puts it here).
    frontend_dir: str = "/opt/frontend"

    database_url: str = "postgresql+psycopg://concierge:concierge@localhost:5433/concierge"
    db_statement_timeout_ms: int = 5000
    tool_timeout_s: float = 10.0
    max_tool_calls_per_turn: int = 4

    # If even the closest chunk scores below this cosine similarity, the question is
    # treated as off-topic and nothing is returned.
    # How it was picked: clearly under the lowest best-chunk score of any answerable
    # question in the two eval sets (0.40), so no answerable question is cut off.
    # It only stops clearly unrelated questions (the MRI question scores 0.25).
    # Whether the passages really answer the question is decided afterwards, by the
    # reply model (NO_ANSWER) and then by the answer check (app/graph/verify.py).
    retrieval_min_similarity: float = 0.30
    # Keyword search merged with dense search (reciprocal rank fusion). False = dense only.
    retrieval_hybrid: bool = True

    # Any OpenAI-compatible endpoint works. LLM_PROVIDER picks a known base URL
    # (cerebras, groq, openai, openrouter); LLM_BASE_URL overrides it for anything else.
    llm_provider: str = "cerebras"
    llm_base_url: str = ""
    llm_api_key: str = ""  # empty is valid: `make eval` must run without a key
    llm_model: str = "qwen-3.8-27b"
    llm_timeout_s: float = 30.0
    # Total budget for the safety check, including one retry and any rate-limit
    # wait. Groq's free tier (8,000 tokens a minute) can make a call wait 7 seconds.
    safety_timeout_s: float = 20.0


@lru_cache
def get_settings() -> Settings:
    """Cached so the env is parsed once. A function (not a module-level
    object) so tests can override it."""
    return Settings()
