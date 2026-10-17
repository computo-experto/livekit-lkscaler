# LiveKit LKScaler Implementation Plan

Date: 2026-06-19
Status: Milestones 1-8 completed, Milestone 9 in progress
Related design spec: ../specs/2026-06-19-livekit-binpack-scaler-design.md

## 1. Objectives

- Build a uv multipackage workspace for livekit-lkscaler.
- Publish a reusable PyPI library named livekit-lkscaler.
- Separate packages:
  - Core bin-packing and ZooKeeper state logic.
  - LiveKit Agent SDK integration hooks.
- Enforce Python 3.12 as minimum supported version.
- Run test validation on every pull request.

## 2. Scope and Constraints

### In scope

- Core package with data model, state store abstraction, bin-pack decision logic, reservation lifecycle handling.
- LiveKit integration package exposing on_request and load_fnc builders.
- Unit and integration tests colocated with each package.
- E2E test suite in a separate top-level folder.
- Docker Compose based test environments.
- Publishing workflow for PyPI.
- Usage and operational documentation.

### Out of scope for this phase

- Heterogeneous capacity weighting.
- Non-self-hosted LiveKit Cloud hosted workers.

## 3. Target Repository Layout

```
lkscaler/
  .github/
    workflows/
      ci.yml
      publish.yml
  docs/
    superpowers/
      specs/
      plans/
  livekit-lkscaler/
    pyproject.toml
    uv.lock
    README.md
    LICENSE
    CHANGELOG.md
    docs/
      usage/
        quickstart.md
        configuration.md
        operations.md
    packages/
      lkscaler-core/
        pyproject.toml
        src/lkscaler_core/
        tests/
          unit/
          integration/
            compose.yaml
      lkscaler-livekit/
        pyproject.toml
        src/lkscaler_livekit/
        tests/
          unit/
          integration/
            compose.yaml
    e2e/
      pyproject.toml
      compose.yaml
      tests/
      fixtures/
    scripts/
      wait_for_services.sh
      run_integration.sh
      run_e2e.sh
```

## 4. Package Boundaries

### 4.1 packages/lkscaler-core

Responsibilities:

- BinpackConfig and validation.
- ZooKeeper path conventions and serialization helpers.
- ZooKeeperStateStore and ClusterSnapshotCache implementation.
- Reservation lifecycle policy:
  - create reservation before accept handoff.
  - remove reservation on accept-without-assignment path.
  - timeout cleanup for reservations while parent session remains alive.
- Placement decision algorithm returning winner/loser load values.

No direct dependency on LiveKit SDK types.

### 4.2 packages/lkscaler-livekit

Responsibilities:

- Adapt core package logic to LiveKit Python Agent SDK interfaces.
- Expose build_on_request_handler and build_load_fnc for AgentServer hooks.
- Map SDK JobRequest behavior into core reservation lifecycle.
- Keep compatibility aliases if desired for legacy naming.

Depends on lkscaler-core and livekit-agents.

### 4.3 e2e

Responsibilities:

- Full system tests with Docker Compose using:
  - ZooKeeper ensemble (3 nodes).
  - LiveKit server.
  - At least 2 agent instances.
- Validate end-to-end bin-pack behavior and failure recovery semantics.

## 5. Dependencies and Tooling

- Workspace manager: uv workspace.
- Python: >= 3.12.
- Lint and formatting: ruff.
- Type checking: mypy.
- Testing: pytest.
- Coverage: pytest-cov.
- ZooKeeper client: kazoo.
- Containerized test orchestration: Docker Compose.

## 6. Test Strategy

### 6.1 Unit tests (both packages)

- Algorithm decisions for winner and loser load values.
- Overflow guard uses >= rule.
- Reservation create-before-accept behavior.
- Reservation deletion when accept does not lead to assignment.
- Timeout cleanup behavior while parent process remains alive.
- Serialization and path mapping correctness.

### 6.2 Integration tests (package-local, ZooKeeper only)

- Use Docker Compose with ZooKeeper only.
- Use mocked request hooks and mocked LiveKit request/accept sequences.
- Validate:
  - reservation and room node transitions.
  - watcher and snapshot convergence.
  - disconnect/reconnect behavior from kazoo client.
  - overflow bound under race windows.

### 6.3 E2E tests (separate folder)

- Compose stack: 3x ZooKeeper + LiveKit server + 2x agents.
- Validate:
  - one agent fills toward target before spillover.
  - loser worker advertises full (1.0) and winner advertises low (0.0).
  - assignment failure path does not leak reservations.
  - crash/termination behavior removes ephemeral nodes.

## 7. CI Plan (Run on Every PR)

PR required checks:

1. Workspace install and lock validation.
2. Ruff format/check.
3. Mypy type check.
4. Unit tests for all packages.
5. Integration tests for all packages (ZooKeeper-only compose).
6. E2E tests with full compose stack.
7. Coverage threshold gate for unit + integration.

Performance and reliability controls:

- Cache uv environment and Docker layers where possible.
- Add explicit health checks and startup waits for ZooKeeper and LiveKit.
- Collect container logs and test artifacts on failure.

## 8. Release and Publishing Plan

- Distribution name: livekit-lkscaler.
- Publish from CI using PyPI Trusted Publisher (OIDC) rather than API tokens.
- Release workflow:
  1. tag-based release trigger.
  2. build wheels and source distribution.
  3. run smoke install test.
  4. publish to TestPyPI then PyPI (or direct if preferred).
- Keep CHANGELOG and semantic versioning.

## 9. Documentation Plan

Minimum docs to ship with v1:

- Quickstart for self-hosted usage.
- Configuration reference with defaults and examples.
- Integration guide with LiveKit AgentServer on_request and load_fnc setup.
- Operational notes for failure handling and troubleshooting.
- Testing guide for local integration and e2e runs.

## 10. Execution Milestones

### Milestone 1: Workspace Bootstrap

Deliverables:

- uv workspace root files.
- package skeletons for lkscaler-core and lkscaler-livekit.
- base lint, type, and test configuration.

Exit criteria:

- CI passes lint/type/tests with placeholder tests.

### Milestone 2: Core Logic Implementation

Deliverables:

- core models, store, cache, and algorithm.
- unit tests for deterministic behavior.

Exit criteria:

- core unit suite green with coverage target met.

### Milestone 3: LiveKit Integration Package

Deliverables:

- hook builders and adapter layer.
- mocked request-hook integration tests.

Exit criteria:

- integration behavior green under ZooKeeper-only compose.

### Milestone 4: E2E Stack and Tests

Deliverables:

- e2e compose stack and test scenarios.
- deterministic service readiness scripts.

Exit criteria:

- E2E suite green in CI on pull requests.

### Milestone 5: Release Readiness

Deliverables:

- packaging metadata complete.
- publish workflow and docs completed.

Exit criteria:

- successful test publish and install verification.

### Milestone 6: External Publish Validation

Deliverables:

- Tag-based publish trigger support for both packages.
- Staged release flow (TestPyPI then PyPI) for tag-triggered runs.
- Release runbook documenting manual and tag-based releases.

Exit criteria:

- Publish workflow supports both workflow_dispatch and tag triggers.
- TestPyPI stage is enforced before PyPI when target is both.
- Release guide includes exact tag naming and local preflight steps.

### Milestone 7: Coverage Gate Enforcement

Deliverables:

- Dedicated coverage gate command for unit+integration scope.
- CI step enforcing minimum coverage threshold.
- Testing guide updates for coverage command and threshold behavior.

Exit criteria:

- `make test-coverage` fails below configured threshold.
- CI includes explicit named coverage gate step.
- Threshold defaults to 90 and is overrideable via `COVERAGE_MIN`.

### Milestone 8: External Publish Execution

Deliverables:

- Local `release-preflight` command combining quality gate + release smoke validation.
- Coordinated publish workflow that builds and publishes both packages together.
- TestPyPI install gate that validates both packages before PyPI publish.
- Release runbook checklist that captures exact workflow dispatch and verification order.

Exit criteria:

- `make release-preflight` is green.
- TestPyPI publish and install gate run in a single workflow for both packages.
- PyPI publish runs only after TestPyPI gate success.
- Checklist is ready for first staged (`testpypi` then `both`) production run.

### Milestone 9: Real-World Integration Proof Gate

Deliverables:

- Production-like integration scenario matrix: steady load, burst load, assignment failures, ZooKeeper reconnect, and parent/job restart behavior.
- Long-running E2E soak scenario validating reservation-to-room transitions and cleanup over repeated churn.
- Automated artifact assertions for occupancy bounds, reservation cleanup latency, and bin-pack trend.
- Release-blocking proof gate command/workflow that must pass before PyPI publish.
- Release runbook update defining PyPI readiness by Milestone 9 proof success.

Exit criteria:

- Real job-process room node behavior is validated end-to-end with repeated runs.
- Bin-pack trend is observed consistently under homogeneous pods (within expected tie/race variance).
- Per-pod occupancy remains bounded by `N + overflow_margin` under stress/fault scenarios.
- ZooKeeper outage fallback remains bounded and converges safely after reconnect.

## 11. Risks and Mitigations

- Slow PR pipeline due to E2E:
  - Mitigation: optimize compose startup, parallelize where safe, cache aggressively.
- Flaky distributed tests:
  - Mitigation: strict health checks, deterministic waits, artifact capture.
- API drift in LiveKit SDK:
  - Mitigation: pin supported version range and add compatibility tests.

## 12. Immediate Next Tasks

1. Define Milestone 9 scenario matrix and pass thresholds aligned to acceptance criteria.
2. Implement one canonical soak path combining burst dispatch + assignment failure + reconnect cycle.
3. Add machine-checked assertions from E2E artifacts for occupancy bound, cleanup latency, and pack trend.
4. Add a proof gate command/workflow that blocks PyPI publish until Milestone 9 passes.
