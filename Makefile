PYTHON ?= python3.11
VENV := .venv
PY := $(VENV)/bin/python

.DEFAULT_GOAL := help

.PHONY: help setup lint lint-js lint-py format format-js format-py typecheck typecheck-js typecheck-py test test-js test-py build check

help:
	@echo "setup       install node and python dependencies"
	@echo "lint        eslint + ruff"
	@echo "format      prettier + ruff format"
	@echo "typecheck   tsc for web/api, mypy for the worker"
	@echo "test        api contract tests + worker tests"
	@echo "build       web production build"
	@echo "check       everything above, in CI order"

setup:
	npm install
	$(PYTHON) -m venv $(VENV)
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e "worker[dev]"

lint: lint-js lint-py

lint-js:
	npm run lint:js

lint-py:
	$(PY) -m ruff check worker

format:
	npm run format:js
	$(PY) -m ruff format worker

typecheck: typecheck-js typecheck-py

typecheck-js:
	npm run typecheck

typecheck-py:
	cd worker && ../$(PY) -m mypy

test: test-js test-py

test-js:
	npm run test:js

test-py:
	$(PY) -m pytest worker/tests

build:
	npm run build

check: lint typecheck test build
	npm run format:js:check
	$(PY) -m ruff format --check worker
