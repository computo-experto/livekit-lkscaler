.PHONY: format lint-check lint-fix typecheck test test-unit test-integration test-e2e test-keda-e2e test-coverage test-proof all-checks milestone-gate proof-gate release-verify release-preflight verify-testpypi-install

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
	uv run pytest packages/lkscaler-core/tests/unit packages/lkscaler-livekit/tests/unit packages/lkscaler-keda/tests/unit

test-integration:
	uv run pytest packages/lkscaler-core/tests/integration packages/lkscaler-livekit/tests/integration packages/lkscaler-keda/tests/integration

test-coverage:
	uv run pytest packages/lkscaler-core/tests/unit packages/lkscaler-core/tests/integration packages/lkscaler-livekit/tests/unit packages/lkscaler-livekit/tests/integration packages/lkscaler-keda/tests/unit packages/lkscaler-keda/tests/integration --cov=lkscaler_core --cov=lkscaler_livekit --cov=lkscaler_keda --cov-report=term-missing --cov-fail-under=$(COVERAGE_MIN)

test-e2e:
	scripts/run_e2e.sh

test-keda-e2e:
	scripts/run_keda_e2e.sh

test-proof:
	bash scripts/run_proof_gate.sh

all-checks: lint-check typecheck test

milestone-gate: format lint-check typecheck test test-coverage test-e2e test-keda-e2e

proof-gate: milestone-gate test-proof

release-verify:
	bash scripts/release_verify.sh

release-preflight: milestone-gate release-verify

verify-testpypi-install:
	bash scripts/verify_testpypi_install.sh "$(PACKAGE)" "$(VERSION)"