# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project follows Semantic Versioning.

## [Unreleased]

### Added

- ZooKeeper coordination backend (`pip install "lkscaler-core[zookeeper]"`): atomic reservation claims,
  TTL expiry cleanup, pod occupancy, and room nodes under `/livekit-binpack/{namespace}`. Unit-tested
  against a fake node client and integration-tested against a real ensemble.
- Coordination contracts shared by every backend: `PodState`, `ClusterStateStore`, and
  `ExpiringReservationStore`, so placement math never learns which backend is running.
- `make test-integration-zookeeper` starts a single-node ZooKeeper on port 22181, runs the backend
  integration tests, and tears the container down; those tests skip cleanly without `LKSCALER_ZK_HOSTS`.
- `docs/usage/coordination.md` documents the contracts, the ZooKeeper layout, cleanup behaviour, and how to
  choose a backend.

### Changed

- `kazoo` moved from a base dependency to the `zookeeper` extra, so a base install no longer downloads a
  client it never imports.

### Added

- Redis coordination backend (`pip install "lkscaler-core[redis]"`): atomic `SET NX` reservation claims,
  TTL-bounded pod occupancy and rooms under `livekit-binpack:{namespace}`, and a `MemoryRedisClient` double
  with a controllable clock so expiry is tested without sleeping. Integration-tested against a real Redis.
- `make test-integration-redis` starts Redis on port 26379, runs the backend integration tests, and removes
  the container; the tests skip cleanly without `LKSCALER_REDIS_URL`.
- `docs/usage/coordination.md` gains Redis setup and the trade-offs between the backends, and states that
  KEDA is a scaler rather than a coordination service.

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
