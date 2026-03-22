.PHONY: install install-dev test lint typecheck dependency-audit fullstack-check run clean

PYTEST_SAFE = PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
PYTEST_OPTS = -p asyncio
PYTEST_COV_OPTS = -p asyncio -p cov

install:
	pip install -e .

install-dev:
	pip install -e ".[all]"

test:
	$(PYTEST_SAFE) python -m pytest $(PYTEST_OPTS) tests/ -v

test-unit:
	$(PYTEST_SAFE) python -m pytest $(PYTEST_OPTS) tests/unit/ -v

test-integration:
	$(PYTEST_SAFE) python -m pytest $(PYTEST_OPTS) tests/integration/ -v

test-e2e:
	$(PYTEST_SAFE) python -m pytest $(PYTEST_OPTS) tests/e2e/ -v

lint:
	ruff check agency_os/ tests/
	ruff format --check agency_os/ tests/

format:
	ruff format agency_os/ tests/

coverage:
	$(PYTEST_SAFE) python -m pytest $(PYTEST_COV_OPTS) tests/ -v --cov=agency_os --cov-report=term-missing

typecheck:
	uvx --from mypy==1.14.1 --with types-PyYAML~=6.0 mypy agency_os/

dependency-audit:
	uvx --from pip-audit pip-audit -r requirements.lock --progress-spinner off
	uvx --from pip-audit pip-audit -r requirements-all.lock --progress-spinner off

fullstack-check: lint typecheck test dependency-audit

run:
	agency-os run

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf build/ dist/ *.egg-info/

