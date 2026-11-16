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
