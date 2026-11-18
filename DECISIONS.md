# Decisions

Each record names what was chosen, the option rejected, and what the choice costs.

## 1. Embeddings run locally, inside the app

**Chosen:** `paraphrase-multilingual-mpnet-base-v2` (768 dimensions), run on CPU inside the app
through ONNX (the fastembed library). The same model embeds document chunks at ingest and the
patient's question at query time; vectors are stored in pgvector on `doc_chunks`.

**Rejected:** a hosted embeddings API (OpenAI or similar). Also rejected, after trying them on
20 English, Hindi and Hinglish questions: `paraphrase-multilingual-MiniLM-L12-v2` (0.2 GB, but
the right passage was top-ranked for only 8 of 14 answerable questions against 11 of 14) and
`multilingual-e5-large` (2.2 GB, two minutes to embed the corpus on CPU, and its scores all
sit between 0.74 and 0.90, so a similarity threshold cannot separate anything).

**Why:** `make eval` must run with no API key, and retrieval is part of the eval. The LLM
provider (Groq) has no embeddings endpoint to reuse. Patients write Hindi and Hinglish against
mostly English documents, so the model has to be multilingual.

**Cost:** the weights are baked into the Docker image, which adds about 1 GB and makes the
first build slower. Embedding the 78 chunks takes about 20 seconds on CPU, paid once at first
start and on every test run. Hinglish is the weak spot: Hinglish questions score lower than
English ones, close to off-topic questions, which limits how well a threshold can abstain.
The vector size is in the schema, so changing the model means a migration and re-embedding.

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

## 4. When the safety classifier fails, we fail closed

**Chosen:** fail closed. If the classifier times out (20 seconds, covering one retry), the
provider errors twice, or its answer is not one of the three verdicts, `safety.classify` returns an outcome with no verdict.
The message is not routed, no tool runs, and the patient gets a fixed, hand-written reply in
their language: we cannot process this right now; if it is an emergency call 112 or the
hospital emergency desk; otherwise try again or call the wellness room for a nurse. Each
failure is logged as one line starting `safety_classifier_failed kind=timeout|error`.

**Rejected:** fail open, letting the message through as if it were SAFE. Then during an outage
"my father collapsed" would be handled as an ordinary message, and a dosage question could be
answered by the main model with no gate in front of it. The gate would be off exactly when
nobody is watching it.

**Why:** the two mistakes are not equal. Blocking a booking costs the patient a retry or a
phone call. Missing an emergency or giving medical advice can hurt someone. The fixed reply
needs no model, so it still works when the provider is down, and it always carries 112.

**Cost:** while the classifier is down the concierge does nothing useful: every booking and
every clinic question is refused, including harmless ones. A real emergency in that window
gets the 112 guidance but no escalation row and no nurse callback, because we do not escalate
on a message we could not classify. A flaky provider therefore shows up directly as refused
messages, which is why failures are logged in a countable form.
