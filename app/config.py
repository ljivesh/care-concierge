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

    # Any OpenAI-compatible endpoint works (Groq, OpenAI, OpenRouter, Ollama...).
    llm_provider: str = "groq"
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_api_key: str = ""  # empty is valid: `make eval` must run without a key
    llm_model: str = ""


@lru_cache
def get_settings() -> Settings:
    """Cached so the env is parsed once. A function (not a module-level
    object) so tests can override it."""
    return Settings()
