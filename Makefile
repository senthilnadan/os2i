PYTHON := .venv/bin/python
PIP := .venv/bin/pip
PYTEST := .venv/bin/pytest
RUFF := .venv/bin/ruff
UVICORN := .venv/bin/uvicorn

.PHONY: install test lint format run

install:
	$(PIP) install -e ".[dev]"

test:
	$(PYTEST)

lint:
	$(RUFF) check .

format:
	$(RUFF) check . --fix

run:
	$(UVICORN) src.transition2exec.api.app:app --reload --port 8002
