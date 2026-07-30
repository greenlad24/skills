# AutoUGC-TH — developer & operator entrypoints.
.PHONY: help install doctor keys start stop restart status open up down migrate test dryrun logs build shell

help:
	@echo "AutoUGC-TH make targets:"
	@echo ""
	@echo "  Onboarding (macOS):"
	@echo "    make install  - one-command Mac setup (Homebrew, Docker, .env, build, start)"
	@echo "    make doctor   - check prerequisites + running services are healthy"
	@echo "    make keys     - interactively add provider API keys / toggle DRY_RUN"
	@echo ""
	@echo "  Run:"
	@echo "    make start    - build + start the full stack (alias: up)"
	@echo "    make stop     - stop the stack, preserving data (alias: down)"
	@echo "    make restart  - restart to apply .env changes"
	@echo "    make status   - show container status"
	@echo "    make open     - open the app in your browser"
	@echo "    make logs     - tail all service logs"
	@echo ""
	@echo "  Dev:"
	@echo "    make migrate  - alembic upgrade head (in the api container)"
	@echo "    make test     - run the pytest suite in the api container"
	@echo "    make dryrun   - run pytest locally with DRY_RUN=true (no Docker, no spend)"
	@echo "    make build    - build images only"
	@echo "    make shell    - open a shell in the api container"

# --- Onboarding ---
install:
	@bash scripts/install-mac.sh

doctor:
	@bash scripts/doctor.sh

keys:
	@bash scripts/configure-keys.sh

# --- Run ---
start up:
	docker compose up -d --build

stop down:
	docker compose down

restart:
	docker compose up -d --build
	@echo "Restarted. Run 'make doctor' to verify."

status:
	docker compose ps

open:
	@open http://localhost:3000 2>/dev/null || echo "Open http://localhost:3000"

logs:
	docker compose logs -f

# --- Dev ---
build:
	docker compose build

migrate:
	docker compose run --rm api alembic upgrade head

test:
	docker compose run --rm api pytest -q

# $0 rehearsal: forces DRY_RUN so every provider returns a deterministic fake.
dryrun:
	DRY_RUN=true pytest -q

shell:
	docker compose run --rm api /bin/bash
