.PHONY: help install dev test test-ci lint fmt clean docker-build docker-up docker-down

# ── Python ──────────────────────────────────────────────────────────────────
PYTHON      := python3
PIP         := pip3
VENV_DIR    := .venv
PY_FLAGS    := -Werror::SyntaxWarning -Werror::ImportWarning

# Detect venv
ifneq ($(wildcard $(VENV_DIR)/bin/python),)
  PYTHON  := $(VENV_DIR)/bin/python
  PIP     := $(VENV_DIR)/bin/pip
endif

# ── Docker ───────────────────────────────────────────────────────────────────
COMPOSE     := docker compose
APP_CONTAINER := nebula-interface

# ── Help ─────────────────────────────────────────────────────────────────────
help:
	@echo "NebulaGraph Interface — Make targets"
	@echo ""
	@echo "  install         Install dependencies (venv or system)"
	@echo "  dev             Run dev server with hot-reload (uvicorn --reload)"
	@echo "  test            Run unit tests (skips integration tests)"
	@echo "  test-all        Run all tests including integration"
	@echo "  test-cov        Run tests with coverage report"
	@echo "  lint            Run linters (ruff, mypy)"
	@echo "  fmt             Auto-format code (ruff)"
	@echo "  clean           Remove __pycache__, .pytest_cache, .ruff_cache"
	@echo "  docker-build    Build Docker image"
	@echo "  docker-up       Start all services (docker compose up -d)"
	@echo "  docker-down     Stop all services"
	@echo "  health          curl http://localhost:8000/health"

# ── Install ──────────────────────────────────────────────────────────────────
install:
	$(PIP) install --upgrade pip
	$(PIP) install -r interface/requirements.txt

# ── Dev ──────────────────────────────────────────────────────────────────────
dev:
	$(PYTHON) -m uvicorn interface.main:app \
		--host 0.0.0.0 --port 8000 --reload \
		--log-level info

# ── Test ─────────────────────────────────────────────────────────────────────
test:
	cd interface && $(PYTHON) -m pytest test/ -v --timeout=30 -m "not integration"

test-all:
	cd interface && $(PYTHON) -m pytest test/ -v --timeout=30

test-cov:
	cd interface && $(PYTHON) -m pytest test/ \
		--timeout=30 -m "not integration" \
		--cov=interface \
		--cov-report=term-missing \
		--cov-report=html

# ── Lint / Format ────────────────────────────────────────────────────────────
lint:
	ruff check interface/
	mypy interface/

fmt:
	ruff format interface/
	ruff check interface/ --fix

# ── Clean ────────────────────────────────────────────────────────────────────
clean:
	find interface/ -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find interface/ -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find interface/ -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf interface/htmlcov/ 2>/dev/null || true
	rm -rf interface/.coverage 2>/dev/null || true

# ── Docker ───────────────────────────────────────────────────────────────────
docker-build:
	$(COMPOSE) -f interface/docker-compose.yml build

docker-up:
	$(COMPOSE) -f interface/docker-compose.yml up -d
	@echo "Waiting for services…"
	@sleep 3
	@curl -s http://localhost:8000/health | python3 -m json.tool

docker-down:
	$(COMPOSE) -f interface/docker-compose.yml down

# ── Health ────────────────────────────────────────────────────────────────────
health:
	@curl -s http://localhost:8000/health | python3 -m json.tool
