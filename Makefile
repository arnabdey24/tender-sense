SHELL := /bin/bash
COMPOSE := docker compose
BACKEND := cd backend &&
.DEFAULT_GOAL := help

.PHONY: help
help: ## Show available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	 | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# --- environment ---
.env: ## Create .env from the template with a generated SECRET_KEY
	@test -f .env || { cp .env.example .env && \
	  python3 -c "import secrets,pathlib; p=pathlib.Path('.env'); p.write_text(p.read_text().replace('SECRET_KEY=','SECRET_KEY='+secrets.token_hex(32),1))" && \
	  echo "created .env with a generated SECRET_KEY"; }

# --- stack ---
.PHONY: dev
dev: .env ## Start the full stack (detached)
	$(COMPOSE) up -d --build

.PHONY: up
up: .env ## Start the stack without rebuilding
	$(COMPOSE) up -d

.PHONY: down
down: ## Stop the stack
	$(COMPOSE) down

.PHONY: clean
clean: ## Stop the stack and delete volumes (destroys the database)
	$(COMPOSE) down -v

.PHONY: logs
logs: ## Tail logs (S=service to filter)
	$(COMPOSE) logs -f $(S)

.PHONY: ps
ps: ## Show container status
	$(COMPOSE) ps

# --- database ---
.PHONY: migrate
migrate: ## Apply migrations inside the stack
	$(COMPOSE) run --rm migrate

.PHONY: migration
migration: ## Autogenerate a migration: make migration M="add users"
	@test -n "$(M)" || { echo 'usage: make migration M="message"'; exit 1; }
	$(COMPOSE) run --rm api alembic revision --autogenerate -m "$(M)"

.PHONY: psql
psql: ## Open a psql shell
	$(COMPOSE) exec db psql -U $${POSTGRES_USER:-tendersense} -d $${POSTGRES_DB:-tendersense}

.PHONY: seed
seed: ## Load the synthetic demo dataset
	$(COMPOSE) run --rm api python -m scripts.seed_demo

.PHONY: superuser
superuser: ## Create or promote platform staff: make superuser EMAIL=you@example.com
	@test -n "$(EMAIL)" || { echo 'Set EMAIL, e.g. make superuser EMAIL=you@example.com'; exit 1; }
	$(COMPOSE) run --rm api python -m scripts.create_superuser --email "$(EMAIL)" $(ARGS)

# --- backend quality ---
.PHONY: install
install: ## Install backend dependencies locally
	$(BACKEND) uv sync

.PHONY: lint
lint: ## Ruff lint + format check + mypy
	$(BACKEND) uv run ruff check . && uv run ruff format --check . && uv run mypy app

.PHONY: format
format: ## Apply ruff formatting and import order
	$(BACKEND) uv run ruff check --fix . && uv run ruff format .

# SQLAlchemy runs async queries inside greenlets, which coverage's default
# tracer does not follow. sys.monitoring reports them accurately.
export COVERAGE_CORE := sysmon

.PHONY: test
test: ## Run backend unit tests
	$(BACKEND) uv run pytest -m "not live" tests/unit

.PHONY: test-all
test-all: ## Run all backend tests including integration (needs Docker)
	$(BACKEND) uv run pytest -m "not live"

.PHONY: bench
bench: ## Time the pipeline against the <60s/tender budget
	$(BACKEND) uv run python -m scripts.bench_process_tender --tenders 3

.PHONY: backup
backup: ## Dump the database and archive the blob volume into ./backups
	./scripts/backup.sh

.PHONY: coverage
coverage: ## Run all backend tests with a coverage report
	$(BACKEND) uv run pytest -m "not live" --cov=app --cov-report=term-missing

# --- frontend ---
.PHONY: fe-install
fe-install: ## Install frontend dependencies
	cd frontend && npm ci

.PHONY: fe-dev
fe-dev: ## Run the Vite dev server
	cd frontend && npm run dev

.PHONY: fe-test
fe-test: ## Run frontend unit tests
	cd frontend && npm test

.PHONY: fe-types
fe-types: ## Regenerate the typed API client from the running API
	cd frontend && npm run api:types

.PHONY: release
release: ## Tag and push a release: make release V=v1.1.0 M="what changed"
	@test -n "$(V)" || { echo 'usage: make release V=v1.1.0 M="what changed"'; exit 1; }
	@test -n "$(M)" || { echo 'usage: make release V=v1.1.0 M="what changed"'; exit 1; }
	@test -z "$$(git status --porcelain)" || { echo 'working tree is dirty'; exit 1; }
	git tag -a "$(V)" -m "$(M)"
	git push origin "$(V)"
	@echo "pushed $(V) — the Release workflow builds and publishes it"

.PHONY: check
check: lint test fe-test ## Everything CI runs
