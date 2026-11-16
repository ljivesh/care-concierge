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

## 3. Double-booking is prevented by a partial unique index in Postgres

**Chosen:** a unique index on `service_requests (clinician_id, scheduled_for) WHERE status =
'BOOKED'`. `app/booking.py` does not check whether a slot is free. It inserts the row; if the
slot is already held, Postgres rejects the insert, and the code reads the constraint name off
the error and turns it into one sentence for the patient with the nearest free slots.

**Rejected:** checking in Python first ("select the slot, and insert if it is empty"). Two
requests in the same instant both see an empty slot and both insert. With the index removed,
our concurrency test writes two rows; with it, one. Also rejected: `SELECT ... FOR UPDATE` or
an advisory lock, which work only if every writer remembers to take the lock.

**Why the database:** it is the one place every writer passes through, whichever process,
script or future service does the writing, so the rule cannot be skipped. The index is partial
so that a cancelled booking frees the slot. Society is left out of it on purpose: a clinician
who visits two societies still has one calendar.

**Cost:** the losing patient finds out only after the insert fails, so the "slot taken" path
is an exception path that has to be handled and tested. The rule is tied to the status values:
a new "active" status (say `CONFIRMED`) needs a migration to the index, or it silently stops
protecting those rows. One lab collection slot is meant to cover several tests, but a second
test at the same slot is rejected like any other double booking; that is a known gap.
