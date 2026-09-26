install:
	uv sync

dev:
	uv run langgraph dev --no-browser --no-reload --n-jobs-per-worker 10

gateway:
	PYTHONPATH=. uv run uvicorn app.gateway.app:app --host 0.0.0.0 --port 8001

test: test-product

test-product:
	PYTHONPATH=. uv run pytest tests/ -v \
		--ignore-glob='tests/test_forge_*.py' \
		--ignore-glob='tests/test_agent_workflow_stage_b_*.py'

lint:
	uvx ruff check .
	uvx ruff format --check .

format:
	uvx ruff check . --fix && uvx ruff format .
