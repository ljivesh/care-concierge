# Care Concierge

A healthcare concierge for residential societies: it books doctor consultations and lab tests,
lists bookings, logs symptoms, answers clinic questions from the document corpus with citations,
refuses to practise medicine, and escalates emergencies into a stored row. It can also show
free slots and cancel or reschedule a booking.

Stack: LangGraph (`StateGraph`, Postgres checkpointer), LangChain (tool binding, structured
output), PostgreSQL 16 with pgvector, Alembic, SQLAlchemy 2, FastAPI with SSE, Docker Compose.

## Run it from a clean clone

The only requirement is Docker with Compose. No API key is needed for the first three commands.

```bash
docker compose up -d --build                    # Postgres + the app
docker compose exec app alembic upgrade head    # already applied at startup; safe to repeat
make eval                                       # replays recorded model outputs; exits 0
make test                                       # 133 tests against a real Postgres
```

Then open http://localhost:8000.

- **First build:** it downloads a 1 GB embedding model into the image, plus the Python and Node
  dependencies, so allow several minutes. After that the stack is healthy in under a minute.
- **Startup does three things before serving,** each safe to repeat: `alembic upgrade head`,
  `python -m app.seed` (3 societies, 12 clinicians, 20 patients) and `python -m app.ingest` (10
  documents into 78 chunks).
- **Ports:** the app is on 8000 and Postgres on 5433. If either is taken, set `APP_HOST_PORT` or
  `DB_HOST_PORT` (in `.env`, or in front of the command).
- **No `make`?** `make eval` is `docker compose exec -T app python -m evals.run`, and `make test`
  is `docker compose exec -T app pytest -q`.

### To chat, add a model key

Without a key the app runs, but every message gets the fail-closed reply, because the safety
check cannot reach a model (see `DECISIONS.md`, record 4).

```bash
cp .env.example .env       # then set LLM_API_KEY
docker compose up -d       # picks up the new settings
```

Any OpenAI-compatible provider works. `LLM_PROVIDER` is one of `cerebras`, `groq`, `openai`,
`openrouter`; for anything else set `LLM_BASE_URL`. The committed eval cache was recorded with
Cerebras and `qwen-3.8-27b`, which are the defaults.

## The three required tests

```bash
docker compose exec -T app pytest -q tests/test_booking.py -k "simultaneous"
docker compose exec -T app pytest -q tests/test_api.py -k "same_request"
docker compose exec -T app pytest -q tests/test_graph.py -k "restart"
docker compose exec -T app pytest -q tests/test_graph.py -k "classifier_failure"
```

| Requirement | Test | File |
|---|---|---|
| Concurrent double-booking | `test_two_simultaneous_bookings_one_row_one_clear_error`, and an eight-way version | `tests/test_booking.py` |
| Duplicate request | `test_same_request_twice_one_booking_and_both_replies_report_it`, and a same-instant version | `tests/test_api.py` |
| Restart and continue | `test_booking_continues_after_a_restart_without_asking_twice` | `tests/test_graph.py` |
| Classifier raises and times out | `test_classifier_failure_blocks_the_message_and_runs_no_tool` (6 cases) | `tests/test_graph.py` |
| A patient cannot read another society | `tests/test_scoping.py`, and the society tests in `tests/test_retrieval.py` | |

Tests use a separate `concierge_test` database that is dropped, rebuilt with
`alembic upgrade head` and seeded on every run. The model calls in tests are scripted fakes; the
graph, checkpointer, tools and database are real.

## The eval

```bash
make eval           # 41 labelled messages, 13 retrieval questions
make eval-fresh     # a second set written after the prompts were fixed
make eval EVAL_ARGS="--intent-file path/to/messages.yaml --retrieval-file path/to/questions.yaml"
```

It prints per-class precision and recall, confusion matrices, every failing row, the retrieval
hit rate at k, and safety false negatives on their own line, and exits 1 when a threshold is
crossed. Rows that were never recorded need `LLM_API_KEY`; without it they are reported as
missing and the run fails. Numbers, failure modes and how far to trust them are in
`EVAL_REPORT.md`. The file format and labelling rules are at the top of
`evals/intent_safety.yaml` and `evals/retrieval.yaml`.

## Where things are

| To answer | Read |
|---|---|
| One booking message, from the page to the row | `app/main.py` (`chat`), `app/chat.py`, `app/graph/nodes.py`, `app/tools.py`, `app/booking.py` (`book`) |
| Can a tool be reached without the safety node? | `app/graph/build.py`: `START` has one edge, to `safety`. `test_no_path_reaches_a_tool_without_passing_safety` |
| Two patients, same slot, same second | The partial unique index in `migrations/versions/0001_initial_schema.py`; the `except IntegrityError` in `app/booking.py`; `DECISIONS.md` record 3 |
| The classifier is down and an emergency arrives | `app/safety.py` (`classify`), `fixed_reply_node` in `app/graph/nodes.py`; `DECISIONS.md` record 4 |
| Society scoping | `app/scoping.py`: every read of bookings or documents, each with a required `society_id` |
| Retrieval | `app/corpus.py` (heading chunks), `app/ingest.py`, `HYBRID_SEARCH_SQL` in `app/scoping.py` |

```
app/            the service: endpoints, graph, tools, booking rules, scoping, retrieval
migrations/     three Alembic migrations
evals/          the eval sets, the harness, and the recorded model outputs
tests/          133 tests
frontend/       the page (React, built into the image)
data/           the corpus and seed files from the bundle
```

## The process dies before the reply is sent

A booking is written, the process dies before the reply goes out, and the patient sends the
same message again. If the retry carries the same `request_id`, as the contract says a retry
does, `stream_turn` in `app/chat.py` sees a turn for that request that started but did not
finish, and resumes the graph from its last checkpoint, which was saved right after the tool
ran. The booking tool does not run again; the model writes the reply from the stored result,
so the patient is told about the one booking that exists. If the checkpoint had been lost too,
`book()` would still find the row by `request_id` and return it, and the unique constraint on
`service_requests.request_id` makes a second row impossible. If the patient instead retypes the
message, it arrives with a new `request_id` and cannot be recognised as a repeat: the insert is
rejected by the slot index, `book()` then checks whether the booking holding that slot is this
patient's own, and replies "you already have this appointment" instead of "that slot was taken".
Both outcomes are right: one booking, and the patient hears about it. What is not covered is a
death before the booking's own transaction commits; then nothing was written, and the retry
simply books. `test_booking_written_then_process_dies_then_patient_resends` and
`test_same_patient_same_slot_new_request_is_told_it_is_already_theirs` exercise the two paths.

## What I cut, and why

- **The no-show pause is not enforced.** A cancellation inside 2 hours is recorded as a no-show,
  as the clinic policy says, but the rule that three no-shows in 90 days pause online booking
  for 30 days is not applied.
- **One lab test per collection slot.** A phlebotomist's home visit is a 15-minute slot, and the
  corpus says one visit covers all the tests booked for that morning. Here each booking is one
  test, so a second test in the same slot is refused like any double booking. It would need the
  unique index to allow several rows for one patient in one slot.
- **Escalations are always Level 1.** The SLA document defines three levels. The contract's
  `escalate_emergency` has no level argument, and the document says to use the higher level
  when unsure and that only a nurse may downgrade.
- **Safety looks at the latest message only.** A follow-up such as "what about two tablets?"
  has no medical words of its own. The reply prompt also forbids medical advice, as a second
  layer, but that layer is not measured by the eval.
- **No login.** This is an MVP, so a patient picker stands in for sign-in.
- **The WhatsApp webhook fixtures** in the data bundle are not used, as the brief allows.
- **Good-to-have rows not done:** the approval step with a LangGraph `interrupt`, and latency
  percentiles. The restart test and the API tests are multi-turn and assert the database's end
  state, but I did not write the two scenario tests as a separate piece.

## What goes beyond the brief

I treated the brief as the floor. Where the product was clearly better with something more, I
added it, and each addition is listed here.

- **Three tools beyond the contract's five,** which are unchanged, with the same names and
  signatures:
  - `find_available_slots` shows free slots, so the patient does not have to guess a time.
  - `cancel_service_request` cancels a booking.
  - `reschedule_service_request` moves a booking to another slot with the same clinician. It
    updates the same row, so the unique index still decides whether the new slot is free.
- **The clinic policy's time rules.** A slot in the past cannot be booked, a booking needs 2
  hours' notice, and a booking can be cancelled or moved free of charge up to 2 hours before.
  Tests freeze the clock (`frozen_clock` in `tests/conftest.py`), so their fixed January 2027
  dates stay valid. An outside test that books a fixed date will be refused once that date has
  passed, which is the behaviour the policy asks for.
- **"You already have this appointment."** A patient who asks again for a slot they hold is told
  so, not that the slot was taken.
- **The frontend is a React app, not one HTML file.** It uses the AI SDK's `useChat` with a
  custom transport (`frontend/src/lib/api/concierge-transport.ts`) that translates the fixed SSE
  events, and shadcn components. It is built inside the Docker image, so nothing extra is needed
  to run it. Tool results are shown as cards: a booking, free slots as buttons, an emergency
  alert with dial links.
- **Hybrid retrieval,** from the good-to-have list: `tsvector` keyword search merged with dense
  search by reciprocal rank fusion. `EVAL_REPORT.md` has the dense-against-hybrid comparison and
  the question dense gets wrong.
- **Tool-call timeline and reload,** also good-to-have rows: each tool call is shown with its
  arguments and result, and a reload restores the conversation from `GET /v1/threads/{id}`.

## How this was built

I built this with an AI coding assistant (Claude Code), one piece at a time, between 16 and 19
November 2026, reading and running each piece before moving to the next. The decisions in
`DECISIONS.md` and the cuts above are mine to defend.
