# AutoUGC-TH — developer entrypoints.
.PHONY: help up down migrate test dryrun logs build shell fmt

help:
	@echo "AutoUGC-TH make targets:"
	@echo "  make up       - build + start the full stack (docker compose up -d)"
	@echo "  make down     - stop the stack (volumes preserved)"
	@echo "  make build    - build images only"
	@echo "  make migrate  - apply DB migrations (alembic upgrade head) in the api container"
	@echo "  make test     - run the pytest suite in the api container"
	@echo "  make dryrun   - run pytest locally with DRY_RUN=true (no Docker, no spend)"
	@echo "  make logs     - tail all service logs"
	@echo "  make shell    - open a shell in the api container"

up:
	docker compose up -d --build

down:
	docker compose down

build:
	docker compose build

migrate:
	docker compose run --rm api alembic upgrade head

test:
	docker compose run --rm api pytest -q

# $0 rehearsal: forces DRY_RUN so every provider returns a deterministic fake.
dryrun:
	DRY_RUN=true pytest -q

logs:
	docker compose logs -f

shell:
	docker compose run --rm api /bin/bash
