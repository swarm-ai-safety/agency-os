.PHONY: install install-dev test lint typecheck dependency-audit verify-node-version frontend-install frontend-test frontend-build fullstack-check run clean backup restore

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

verify-node-version:
	./scripts/site-install.sh --check-only

frontend-install:
	./scripts/site-install.sh

frontend-build:
	@$(MAKE) frontend-install
	rm -rf site/.next site/.next-build-check
	cd site && env -u npm_config_auto_install_peers -u npm_config_recursive npm run build

frontend-test:
	@$(MAKE) frontend-install
	cd site && env -u npm_config_auto_install_peers -u npm_config_recursive npm run test:coverage

fullstack-check: verify-node-version lint typecheck test dependency-audit frontend-test frontend-build

run:
	agency-os run

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf build/ dist/ *.egg-info/

backup:
	@./scripts/backup-database.sh

restore:
	@echo "Available backups:"
	@ls -1t backups/agency_os-*.db 2>/dev/null || echo "  No backups found"
	@echo ""
	@echo "To restore, run:"
	@echo "  cp backups/agency_os-YYYYMMDD-HHMMSS.db agency_os.db"
	@echo ""
	@echo "See docs/disaster-recovery.md for full restore procedure"
