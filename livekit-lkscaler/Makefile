.PHONY: format lint-check lint-fix typecheck test test-unit test-integration test-e2e test-coverage all-checks milestone-gate release-verify release-preflight verify-testpypi-install

COVERAGE_MIN ?= 90

format:
	uv run ruff format .

lint-check:
	uv run ruff check .

lint-fix:
	uv run ruff check . --fix

typecheck:
	uv run mypy .

test:
	uv run pytest

test-unit:
	uv run pytest packages/lkscaler-core/tests/unit packages/lkscaler-livekit/tests/unit

test-integration:
	uv run pytest packages/lkscaler-core/tests/integration packages/lkscaler-livekit/tests/integration

test-coverage:
	uv run pytest packages/lkscaler-core/tests/unit packages/lkscaler-core/tests/integration packages/lkscaler-livekit/tests/unit packages/lkscaler-livekit/tests/integration --cov=lkscaler_core --cov=lkscaler_livekit --cov-report=term-missing --cov-fail-under=$(COVERAGE_MIN)

test-e2e:
	scripts/run_e2e.sh

all-checks: lint-check typecheck test

milestone-gate: format lint-check typecheck test test-coverage test-e2e

release-verify:
	bash scripts/release_verify.sh

release-preflight: milestone-gate release-verify

verify-testpypi-install:
	bash scripts/verify_testpypi_install.sh "$(PACKAGE)" "$(VERSION)"