# Everything runs inside the app container, so the only local requirement is Docker.

.PHONY: up down test

up:
	docker compose up -d --build

down:
	docker compose down

test:
	docker compose exec -T app pytest -q
