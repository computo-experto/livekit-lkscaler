.PHONY: help format lint-check lint-fix typecheck test test-unit test-integration test-integration-zookeeper test-integration-redis test-e2e test-e2e-backends test-real-agent-wiring test-real-agent-scenarios test-keda-scale-e2e test-coverage test-proof all-checks milestone-gate proof-gate release-verify release-preflight verify-testpypi-install

.DEFAULT_GOAL := help

COVERAGE_MIN ?= 90

help: ## List available targets
	@echo "Targets:"
	@awk 'BEGIN {FS = ":.*?## "}; /^[a-zA-Z][a-zA-Z0-9_-]*:.*?## / {printf "  \033[36m%-28s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

format: ## Format Python sources with ruff
	uv run ruff format .

lint-check: ## Lint with ruff, changing nothing
	uv run ruff check .

lint-fix: ## Lint with ruff and apply safe fixes
	uv run ruff check . --fix

typecheck: ## Type-check the workspace with mypy (strict)
	uv run mypy .

test: ## Run everything pytest collects by default
	uv run pytest

test-unit: ## Run the package unit tests
	uv run pytest packages/lkscaler-core/tests/unit packages/lkscaler-livekit/tests/unit packages/lkscaler-keda/tests/unit

test-integration: ## Run the package integration tests (skip without an external service)
	uv run pytest packages/lkscaler-core/tests/integration packages/lkscaler-livekit/tests/integration

test-integration-zookeeper: ## Run the ZooKeeper backend tests against a real ensemble
	bash scripts/run_zookeeper_integration.sh

test-integration-redis: ## Run the Redis backend tests against a real server
	bash scripts/run_redis_integration.sh

test-coverage: ## Enforce the coverage floor on the unit and integration suites
	uv run pytest packages/lkscaler-core/tests/unit packages/lkscaler-core/tests/integration packages/lkscaler-livekit/tests/unit packages/lkscaler-livekit/tests/integration --cov=lkscaler_core --cov=lkscaler_livekit --cov-report=term-missing --cov-fail-under=$(COVERAGE_MIN)

test-e2e: ## Run the compose-backed end-to-end suite
	scripts/run_e2e.sh

test-e2e-backends: ## Run the coordination end-to-end suite against each backend
	bash scripts/run_e2e_backends.sh

test-real-agent-wiring: ## Run the stack-free real-agent wiring tests
	uv run pytest e2e/tests/test_real_agent_wiring.py

test-real-agent-scenarios: ## Run the real-agent scenario suite against the compose stack
	bash scripts/run_e2e_real_agents.sh

test-keda-scale-e2e: ## Prove KEDA scales real workers up and down in kind
	bash scripts/run_keda_scale_e2e.sh

test-proof: ## Run the end-to-end suite plus the Milestone 9 proof-gate assertions
	bash scripts/run_proof_gate.sh

all-checks: lint-check typecheck test ## Run lint, typecheck and tests

milestone-gate: format lint-check typecheck test test-coverage test-e2e ## Run the full per-milestone gate

proof-gate: milestone-gate test-proof test-real-agent-scenarios test-keda-scale-e2e ## Run the milestone gate, the real-agent scenarios, the proof assertions and the KEDA scale proof

release-verify: ## Build and smoke-install both published packages
	bash scripts/release_verify.sh

release-preflight: milestone-gate release-verify ## Run the milestone gate and release verification

verify-testpypi-install: ## Verify an install from TestPyPI (PACKAGE=..., VERSION=...)
	bash scripts/verify_testpypi_install.sh "$(PACKAGE)" "$(VERSION)"
