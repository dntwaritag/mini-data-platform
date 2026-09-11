SHELL := /bin/bash
COMPOSE := docker compose
PYTHON := python3

.PHONY: help
help: ## Show this help
	@echo "Mini Data Platform — available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

.PHONY: build
build: ## Build all Docker images
	$(COMPOSE) build

.PHONY: up
up: ## Start the full platform in the background
	$(COMPOSE) up -d
	@echo "Airflow:  http://localhost:$${AIRFLOW_WEBSERVER_PORT:-8080}"
	@echo "MinIO:    http://localhost:$${MINIO_CONSOLE_PORT:-9001}"
	@echo "Metabase: http://localhost:$${METABASE_PORT:-3000}"

.PHONY: down
down: ## Stop all services (keeps volumes/data)
	$(COMPOSE) down

.PHONY: restart
restart: down up ## Restart the full platform

.PHONY: logs
logs: ## Tail logs for all services
	$(COMPOSE) logs -f --tail=200

.PHONY: ps
ps: ## Show status of all services
	$(COMPOSE) ps

.PHONY: generate-data
generate-data: ## Generate a synthetic sales CSV (data/sales.csv)
	$(PYTHON) data_generator/generate_sales.py --rows $${ROWS:-1000} --seed $${SEED:-42} --output data/sales.csv

.PHONY: upload-data
upload-data: ## Upload data/sales.csv into the MinIO raw-data bucket
	$(PYTHON) scripts/init_minio.py --file data/sales.csv --endpoint localhost:$${MINIO_API_PORT:-9000}

.PHONY: init-metabase
init-metabase: ## Best-effort automated Metabase setup (falls back to manual instructions)
	$(PYTHON) scripts/init_metabase.py --metabase-url http://localhost:$${METABASE_PORT:-3000}

.PHONY: pipeline
pipeline: generate-data upload-data ## Generate + upload data, then trigger the Airflow DAG
	docker exec mdp-airflow-webserver airflow dags unpause sales_pipeline
	docker exec mdp-airflow-webserver airflow dags trigger sales_pipeline

.PHONY: test
test: ## Run unit tests
	$(PYTHON) -m pytest tests/unit -v

.PHONY: lint
lint: ## Lint Python code with ruff
	ruff check .

.PHONY: integration-test
integration-test: ## Run integration tests against a running platform (requires `make up` first)
	$(PYTHON) -m pytest tests/integration -v

.PHONY: clean
clean: ## Remove local caches and generated data (keeps Docker volumes)
	rm -rf .pytest_cache .ruff_cache **/__pycache__ data/*.csv
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +

.PHONY: reset
reset: ## Stop the platform and DELETE all persistent volumes (irreversible)
	$(COMPOSE) down -v
