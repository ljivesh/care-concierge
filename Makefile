# Everything runs inside the app container, so the only local requirement is Docker.

.PHONY: up down test eval eval-fresh

up:
	docker compose up -d --build

down:
	docker compose down

test:
	docker compose exec -T app pytest -q

# Replays recorded model outputs, so it needs no API key. To run other files:
#   make eval EVAL_ARGS="--intent-file path/to/messages.yaml --retrieval-file path/to/questions.yaml"
# (rows that were never recorded need LLM_API_KEY set in .env)
eval:
	docker compose exec -T app python -m evals.run $(EVAL_ARGS)

# The second set, written after the prompts were fixed: see EVAL_REPORT.md.
# Add --dense-only (via EVAL_ARGS on `make eval`) to see the scores before hybrid search.
eval-fresh:
	docker compose exec -T app python -m evals.run --intent-file evals/fresh_intent_safety.yaml --retrieval-file evals/fresh_retrieval.yaml
