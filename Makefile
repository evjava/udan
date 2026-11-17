lib_name=$$(grep -oP '(?<=^name = ").*(?=")' pyproject.toml)
version=$$(grep -oP '(?<=^version = ").*(?=")' pyproject.toml)
pypi_command="curl -s https://pypi.org/rss/project/$(lib_name)/releases.xml | grep '<title>' | head -n 2 | grep -oP '(?<=title>)\d+.\d+.\d+(?=</title)'"

UV = env -u VIRTUAL_ENV uv

# `make pre failfast=0` runs every hook and reports all failures instead of stopping at the first
FAILFAST = $(if $(failfast),--fail-fast=$(failfast))
# `make pre filter=ruff` runs only the hooks whose id matches the regex
FILTER = $(if $(filter),--filter=$(filter))

.PHONY: help install vulture-unused impl-to-impl i-to-i lines test test-all test-cov lint format pre-commit-install check-all pre pre-commit ty-check check-types check-ruff-format check-ruff-check check-style check-tests check-encapsulation encap datty-py datty-md clear-pycache

# Show this help message
help:
	@echo "Available targets:"
	@awk '/^# [A-Za-z]/ {desc=$$0; getline; if (/^[a-z][a-z0-9_-]+:/) {target=substr($$0, 1, index($$0, ":")-1); printf "  %-25s %s\n", target, substr(desc, 3)}}' $(MAKEFILE_LIST)

## INSTALL

# Refresh stale copies first: a plain sync/install skips udan when 0.1.0 is already
# installed, so console scripts go stale across entry-point renames (udan.queries.main).
# Install udan as a `udan` script on PATH (uv tool install, editable from this repo)
install:
	uv sync --reinstall-package udan
	@if [ -n "$$VIRTUAL_ENV" ]; then \
		echo "Refreshing udan in the active venv: $$VIRTUAL_ENV"; \
		uv pip install --reinstall-package udan -e . || echo "Could not refresh udan in $$VIRTUAL_ENV, skipped"; \
	fi
	uv tool install --editable .
	@resolved=$$(command -v udan || true); \
	if [ -n "$$resolved" ] && grep -q "udan.queries" "$$resolved"; then \
		echo "WARNING: $$resolved is a stale udan script (udan.queries); refresh or remove it in that environment"; \
	fi

build:
	rm -rf ./dist
	uv build

## QUALITY

# Show unused code via vulture (same check as `make pre`)
vulture-unused:
	uv run python tools/run_checks.py vulture

# Show impl-to-impl dependencies (ignores adhoc exceptions, same hook as `make pre`)
impl-to-impl:
	uv run python tools/run_checks.py forbid-impl-in-impl --arg=--no-adhocs
i-to-i: impl-to-impl

# Lines
lines:
	bash tools/udan-count-lines.sh

## CHECKS

# Run unit tests (parallel with xdist, affected tests first via testmon)
test:
	uv run pytest -n auto --testmon --no-cov

# Run all tests (unit + integration)
test-all:
	uv run pytest -n auto tests/ --testmon --no-cov
# DISABLED:	uv run pytest tests-integration/ --integration -v --no-cov

# Run integration tests (serial) - DISABLED
# test-integration:
# 	uv run pytest tests-integration/ --integration -v --no-cov

# Run tests with coverage report
test-cov:
	uv run pytest --cov=src --cov-report=html --cov-report=term

# Run linter (alias for check-ruff-check)
lint: check-ruff-check

# Format code (same paths as the ruff-format hook)
format:
	uv run ruff format src/ tests/ tools/ checks/ .claude/hooks/

pre-commit-install:
	uv run python tools/install_hooks.py

# Run all hooks from .pre-commit-config.yaml (stops on first failure unless failfast=0, no git needed; filter=REGEX runs matching hooks only)
check-all:
	$(UV) run python tools/run_checks.py $(FAILFAST) $(FILTER)
pre pre-commit: check-all

# Run ty hook
ty-check:
	uv run python tools/run_checks.py ty

# Check types with ty (same check as `make pre`)
check-types: ty-check

# Check formatting with ruff (same paths as the ruff-format hook)
check-ruff-format:
	uv run ruff format --check src/ tests/ tools/ checks/ .claude/hooks/

# Check linting with ruff
check-ruff-check:
	uv run ruff check src/ tests/

# Check other hooks (except ruff and pytest)
check-style:
	uv run python tools/run_checks.py --skip '^(ruff|pytest)'

# Run pytest on tests/ (adds --no-cov when FILE or K is passed)
check-tests:
	@extra_args=; \
	if [ -n "$(FILE)" ] || [ -n "$(K)" ]; then \
		extra_args="--no-cov"; \
	fi; \
	uv run pytest tests/ -v -x $$extra_args $(if $(FILE),$(FILE),) $(if $(K),-k $(K),)

# Run pytest on tests-integration/ - DISABLED
# check-tests-int:
# 	uv run pytest tests-integration/ --integration -v -x --no-cov

# Check encapsulation violations (protected attribute access)
check-encapsulation:
	uv run python tools/run_checks.py check-encapsulation-violations
encap: check-encapsulation

## UTILITIES

# Print datty date prefix for Python files (plg_yyyy_mm_dd__HH_MM__)
datty-py:
	@echo "plg_$$(date '+%Y_%m_%d__%H_%M__')"

# Print datty date prefix for docs (yyyy-mm-dd--HH-MM--)
datty-md:
	@date '+%Y-%m-%d--%H-%M--'

# Clear Python caches
clear:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache htmlcov .ruff_cache .udan_cache
	@echo "Python cache cleared"

pypi:
	eval "$(pypi_command)"


# Catch unknown targets and suggest similar ones via Levenshtein distance
.DEFAULT:
	@python3 tools/suggest_target.py "$(MAKECMDGOALS)"
