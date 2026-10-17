# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project follows Semantic Versioning.

## [Unreleased]

### Added

- ZooKeeper coordination backend (`pip install "lkscaler-core[zookeeper]"`): atomic reservation claims,
  TTL expiry cleanup, pod occupancy, and room nodes under `/livekit-binpack/{namespace}`. Unit-tested
  against a fake node client and integration-tested against a real ensemble.
- Coordination contracts shared by every backend: `PodState` and `ClusterStateStore`, plus TTL cleanup
  folded into `ReservationStore` so placement math never learns which backend is running.
- `make test-integration-zookeeper` starts a single-node ZooKeeper on port 22181, runs the backend
  integration tests, and tears the container down; those tests skip cleanly without `LKSCALER_ZK_HOSTS`.
- `docs/usage/coordination.md` documents the contracts, the ZooKeeper layout, cleanup behaviour, and how to
  choose a backend.
- Redis coordination backend (`pip install "lkscaler-core[redis]"`): atomic `SET NX` reservation claims,
  TTL-bounded pod occupancy and rooms under `livekit-binpack:{namespace}`, and a `MemoryRedisClient` double
  with a controllable clock so expiry is tested without sleeping. Integration-tested against a real Redis.
- `make test-integration-redis` starts Redis on port 26379, runs the backend integration tests, and removes
  the container; the tests skip cleanly without `LKSCALER_REDIS_URL`.
- Cross-process coordination E2E: two backend-wired agents (`e2e/fixtures/packed_agent.py`) drive the real
  `reserve_for_admission` and `build_load_fnc` against a selected backend and expose them over HTTP, so
  `e2e/tests/test_e2e_backends.py` asserts the cluster view the backend actually holds: fill-before-spillover,
  the overflow bound, cross-worker visibility, claim release, TTL expiry, and a killed worker leaving the
  cluster view (ZooKeeper session close, Redis TTL).
- `make test-e2e-backends` runs that suite once per backend through the compose `backends` profile, which
  adds `redis` and the two packed agents without touching the default six-service stack, and captures
  per-backend artifacts under `e2e/artifacts/backends/`.

### Changed

- `kazoo` moved from a base dependency to the `zookeeper` extra, so a base install no longer downloads a
  client it never imports.
- Licensing settled on Apache-2.0 and made consistent: the repo previously shipped an abridged Apache-2.0
  text in one file while all three packages declared MIT, and no license text reached the artifacts. The
  canonical Apache-2.0 text now sits at the repository root and in every package, packages use PEP 639
  metadata (`license = "Apache-2.0"`, `license-files`), the deprecated MIT classifier is gone, and both
  `LICENSE` and `NOTICE` ship in the wheels and sdists.

### Removed

- The `lkscaler-keda` package and its KEDA kind E2E harness are gone, along with the `make test-keda-e2e`
  target, the CI step that ran it, and the `kind`/`kubectl`/`envsubst` installs that existed only to support
  it. Nothing in the repository served the package's external-scaler interface over gRPC, its `ScaledObject`
  pointed at a Service that no workload provided, and the kind suite asserted a manual `kubectl scale`
  rather than an autoscaling integration. The `load_fnc` value a worker reports remains the signal any
  replica manager (Kubernetes HPA, KEDA, or LiveKit's own scaling) reacts to.
- The unused `kubernetes` e2e dependency, which only the removed KEDA test environment needed.

### Fixed

- The E2E agent image built an empty virtualenv: `uv sync --frozen --no-dev` syncs only the workspace root
  project, which declares no dependencies, so every agent container failed at import. It now syncs with
  `--all-packages`, and the backend-wired agents run on `/app/.venv/bin/python`. The pre-existing
  `agent1`/`agent2` services are deliberately left as-is so this change does not alter what the existing E2E
  assertions observe.
- `ReservationStore` declares `remove_expired` as part of the contract, replacing the separate
  `ExpiringReservationStore` protocol that added a second name for the same thing.

## [0.2.0] - 2026-10-17

### Added

- KEDA autoscaler integration package (`lkscaler-keda`): free-slot policy, KEDA external scaler interface,
  pod deletion cost reconciler, and ScaledObject/RBAC manifests.
- Cluster snapshot summary API (`lkscaler_core.summarize_cluster_snapshot`) that the KEDA policy consumes.

### Changed

- `lkscaler-core` and `livekit-lkscaler` are released as one coordinated set: a single Publish run builds
  both, uploads both to TestPyPI, gates on installing both from TestPyPI, then uploads both to PyPI.
- Publish triggers are now `workflow_dispatch` (`testpypi` | `both`) and `release-vX.Y.Z` tags. Pushes to
  `main` no longer publish.
- Release verification fails when the two released packages do not share one version.
- Package metadata and documentation: each published package ships a full user guide as its PyPI long
  description (install, why the project exists, concepts, runnable quickstart, API, behavior contract,
  operational notes), the one-line summaries state the benefit (bin-packed jobs, faster scale-down), and
  project URLs point at the real public repository instead of the stale `github.com/jmedina/lkscaler` links
  that returned 404.
- Documentation now matches what ships on coordination and scaling: ZooKeeper is described as the designed
  shared-state backend rather than a shipped requirement (`lkscaler-core` bundles only an in-memory,
  single-process store and no ZooKeeper client), `BinpackConfig.zk_session_timeout_sec`,
  `sync_interval_ms`, and `fail_mode` are marked as unread by the shipped helpers, and KEDA is described
  as optional rather than required for placement or scale-down.

### Fixed

- PyPI publishing no longer aborts on the already-released file that left `lkscaler-core` missing while
  `livekit-lkscaler` was published: both distributions now move together in one versioned release.

## [0.1.0] - 2026-06-20

### Added

- Milestone 5 release readiness: publish workflow with OIDC trusted publishing for TestPyPI/PyPI, package
  metadata enrichment for `lkscaler-core` and `livekit-lkscaler`, release smoke verification script and
  the `make release-verify` target, and usage documentation for quickstart, configuration, and operations.
