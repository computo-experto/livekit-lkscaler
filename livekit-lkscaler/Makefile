.PHONY: format lint-check lint-fix typecheck test test-unit test-integration test-integration-zookeeper test-integration-redis test-e2e test-e2e-backends test-real-agent-wiring test-coverage test-proof all-checks milestone-gate proof-gate release-verify release-preflight verify-testpypi-install

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

test-integration-zookeeper:
	bash scripts/run_zookeeper_integration.sh

test-integration-redis:
	bash scripts/run_redis_integration.sh

test-coverage:
	uv run pytest packages/lkscaler-core/tests/unit packages/lkscaler-core/tests/integration packages/lkscaler-livekit/tests/unit packages/lkscaler-livekit/tests/integration --cov=lkscaler_core --cov=lkscaler_livekit --cov-report=term-missing --cov-fail-under=$(COVERAGE_MIN)

test-e2e:
	scripts/run_e2e.sh

test-e2e-backends:
	bash scripts/run_e2e_backends.sh

test-real-agent-wiring:
	uv run pytest e2e/tests/test_real_agent_wiring.py

test-proof:
	bash scripts/run_proof_gate.sh

all-checks: lint-check typecheck test

milestone-gate: format lint-check typecheck test test-coverage test-e2e

proof-gate: milestone-gate test-proof

release-verify:
	bash scripts/release_verify.sh

release-preflight: milestone-gate release-verify

verify-testpypi-install:
	bash scripts/verify_testpypi_install.sh "$(PACKAGE)" "$(VERSION)"