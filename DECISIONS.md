# Decisions

Each record names what was chosen, the option rejected, and what the choice costs.

## 1. Embeddings run locally, inside the app

**Chosen:** a small multilingual embedding model loaded in the app process and run on CPU.
The same model embeds document chunks at ingest and the patient's question at query time;
vectors are stored in pgvector on `doc_chunks`. Exact model and library are confirmed in the
retrieval step, after testing on the Hindi questions.

**Rejected:** a hosted embeddings API (OpenAI or similar).

**Why:** `make eval` must run with no API key, and retrieval is part of the eval. The LLM
provider (Groq) has no embeddings endpoint to reuse. The corpus is about 100 chunks, so CPU
speed is not a concern. Patients write Hindi and Hinglish against mostly English documents,
so the model has to be multilingual.

**Cost:** a larger Docker image and slower first build, because the weights are baked in.
A small local model is weaker than a large hosted one, so cross-language matches (a Hindi
question against an English passage) are the most likely retrieval misses. Changing the model
later means re-embedding every chunk and re-picking the similarity threshold.

## 2. Groq as the LLM provider, switchable from the env file

**Chosen:** Groq, reached through its OpenAI-compatible endpoint. Provider, base URL, key and
model are four env vars (`LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`) read in
`app/config.py`. Moving to another OpenAI-compatible provider is an env change, not a code
change. The model name is set when the LLM is first wired in.

**Rejected:** coding against one provider's own SDK (for example OpenAI or Anthropic directly).

**Why:** Groq has a free tier, and that is the only reason it is the default. Model choice is
not graded, so nothing here depends on Groq specifically. Keeping the provider in config means
it can be replaced with any LLM, and a grader can run it with whatever key they have.

**Cost:** the open-weight models Groq hosts are less reliable than frontier models at tool
calling, structured output and Hinglish, so more of the correctness has to come from our own
validation (Pydantic schemas, retries, the tool-call cap). Staying on the OpenAI-compatible
surface means no provider-specific features. The eval cache is recorded against one model, so
switching model makes the committed numbers stale until the eval is re-recorded.
