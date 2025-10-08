.PHONY: help install migrate seed run test fmt lint clean

help:  ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install:  ## Install dependencies
	pip install -r requirements.txt

migrate:  ## Run database migrations
	python manage.py migrate

seed:  ## Seed database with test data
	python manage.py seed_data

run:  ## Run development server
	python manage.py runserver

test:  ## Run tests
	pytest

fmt:  ## Format code with black
	black .

lint:  ## Lint code with ruff
	ruff check .

lint-fix:  ## Lint and fix code with ruff
	ruff check --fix .

typecheck:  ## Type check with mypy
	mypy .

clean:  ## Clean up generated files
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .mypy_cache .ruff_cache
	rm -f db.sqlite3

superuser:  ## Create a superuser
	python manage.py createsuperuser

shell:  ## Open Django shell
	python manage.py shell

worker:  ## Start Celery worker
	celery -A server worker -l info

all:  ## Install, migrate, seed, and run
	make install
	make migrate
	make seed
	make run
