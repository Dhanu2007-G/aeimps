.PHONY: help dev dev-build down logs ps \
        migrate migrate-create seed reset-db \
        test test-unit test-integration test-eval \
        lint format typecheck \
        create-api-key benchmark

SHELL := /bin/bash
.DEFAULT_GOAL := help

# ─── Colors ──────────────────────────────────────────────────
BLUE  := \033[34m
GREEN := \033[32m
RESET := \033[0m

help: ## Show this help message
	@echo -e "$(BLUE)AEIMPS Development Commands$(RESET)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-25s$(RESET) %s\n", $$1, $$2}'

# ─── Environment Setup ────────────────────────────────────────
.env:
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo -e "$(GREEN)Created .env from .env.example — please fill in your values$(RESET)"; \
	fi

setup: .env ## Initial setup: copy .env, create dirs
	@mkdir -p data/raw data/models
	@echo -e "$(GREEN)Setup complete$(RESET)"

# ─── Docker Compose ──────────────────────────────────────────
dev: setup ## Start all services in development mode (build if needed)
	docker compose up -d
	@echo -e "$(GREEN)Services starting...$(RESET)"
	@echo "  API:       http://localhost:8000"
	@echo "  API Docs:  http://localhost:8000/docs"
	@echo "  Frontend:  http://localhost:3000"
	@echo "  Grafana:   http://localhost:3001"
	@echo "  Neo4j:     http://localhost:7474"
	@echo "  Qdrant:    http://localhost:6333"

dev-build: setup ## Build and start all services
	docker compose up -d --build

infra-only: setup ## Start only infrastructure services (no app workers)
	docker compose up -d postgres redis qdrant neo4j prometheus grafana otel-collector
	@echo -e "$(GREEN)Infrastructure services started$(RESET)"

down: ## Stop all services
	docker compose down

down-volumes: ## Stop all services and delete volumes (DESTRUCTIVE)
	docker compose down -v
	@echo -e "$(GREEN)All services stopped and volumes removed$(RESET)"

logs: ## Tail all service logs
	docker compose logs -f

logs-api: ## Tail API logs
	docker compose logs -f api

logs-workers: ## Tail all worker logs
	docker compose logs -f worker-doc-processor worker-embedding worker-kg worker-vision

ps: ## Show running services
	docker compose ps

restart-api: ## Restart the API service
	docker compose restart api

# ─── Database ────────────────────────────────────────────────
migrate: ## Run Alembic migrations
	docker compose exec api alembic upgrade head
	@echo -e "$(GREEN)Migrations complete$(RESET)"

migrate-create: ## Create a new migration (use MSG="your message")
	docker compose exec api alembic revision --autogenerate -m "$(MSG)"

migrate-down: ## Rollback last migration
	docker compose exec api alembic downgrade -1

migrate-history: ## Show migration history
	docker compose exec api alembic history

seed: ## Seed sample data
	docker compose exec api python /app/scripts/seed_data.py
	@echo -e "$(GREEN)Seed data loaded$(RESET)"

reset-db: ## DANGER: Drop and recreate database
	@echo -e "\033[31mWARNING: This will destroy all data!\033[0m"
	@read -p "Type 'yes' to confirm: " confirm; \
	if [ "$$confirm" = "yes" ]; then \
		docker compose exec api python /app/scripts/reset_db.py; \
		echo -e "$(GREEN)Database reset complete$(RESET)"; \
	else \
		echo "Cancelled"; \
	fi

# ─── API Keys ─────────────────────────────────────────────────
create-api-key: ## Create a new API key (use NAME="my-key")
	docker compose exec api python /app/scripts/create_api_key.py --name "$(NAME)"

# ─── Testing ─────────────────────────────────────────────────
test: ## Run all tests
	cd backend && python -m pytest tests/ -v --tb=short

test-unit: ## Run unit tests only
	cd backend && python -m pytest tests/unit/ -v --tb=short

test-integration: ## Run integration tests (requires running services)
	cd backend && python -m pytest tests/integration/ -v --tb=short

test-eval: ## Run evaluation suite
	cd backend && python tests/evaluation/run_eval.py

benchmark: ## Run retrieval benchmark
	docker compose exec api python /app/scripts/benchmark_retrieval.py

# ─── Code Quality ────────────────────────────────────────────
lint: ## Run ruff linter
	cd backend && ruff check app/ workers/

format: ## Format code with ruff
	cd backend && ruff format app/ workers/

typecheck: ## Run mypy type checking
	cd backend && mypy app/ workers/ --ignore-missing-imports

# ─── Utilities ───────────────────────────────────────────────
init-collections: ## Initialize Qdrant collections and Neo4j constraints
	docker compose exec api python -c "from app.db.qdrant import init_collections; import asyncio; asyncio.run(init_collections())"
	docker compose exec api python -c "from app.db.neo4j import init_constraints; import asyncio; asyncio.run(init_constraints())"

health: ## Check system health
	@curl -sf http://localhost:8000/api/v1/admin/health | python3 -m json.tool || echo "API not ready"

shell-api: ## Open a shell in the API container
	docker compose exec api bash

shell-postgres: ## Open a psql shell
	docker compose exec postgres psql -U ${POSTGRES_USER:-aeimps} -d ${POSTGRES_DB:-aeimps}
