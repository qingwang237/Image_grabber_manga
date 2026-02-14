.PHONY: help install lint format check test test-cov clean

help:  ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install:  ## Install package with dev dependencies
	pip install -e ".[dev]"

lint:  ## Run ruff linter
	ruff check .

format:  ## Format code with ruff
	ruff format .

format-check:  ## Check code formatting without making changes
	ruff format --check .

check:  ## Run both linter and format check
	ruff check .
	ruff format --check .

fix:  ## Auto-fix linting issues where possible
	ruff check --fix .
	ruff format .

test:  ## Run tests with pytest
	uv run pytest

test-cov:  ## Run tests with coverage report
	uv run pytest --cov=wgrabber --cov-report=term-missing --cov-report=html

test-verbose:  ## Run tests in verbose mode
	pytest -v

clean:  ## Clean up cache and coverage files
	rm -rf .pytest_cache
	rm -rf .ruff_cache
	rm -rf htmlcov
	rm -rf .coverage
	rm -rf **/__pycache__
	rm -rf **/*.pyc
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

all: clean install check test  ## Run clean, install, check, and test
