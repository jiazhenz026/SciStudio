.PHONY: install lint typecheck test serve

install:
	pip install -e ".[dev]"

lint:
	ruff check src/ tests/
	ruff format --check src/ tests/

typecheck:
	mypy src/scistudio/

test:
	pytest

serve:
	uvicorn scistudio.api.app:create_app --factory --reload --host 0.0.0.0 --port 8000
