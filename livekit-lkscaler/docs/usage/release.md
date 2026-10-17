# Release Guide

This guide covers the coordinated release flow for `lkscaler-core`, `livekit-lkscaler` and `lkscaler-keda`. All three
always ship together at one shared version.

## Release triggers

- Manual: run the Publish workflow via workflow_dispatch and choose target (`testpypi` or `both`).
- Tag-based: push `release-vX.Y.Z` to run the staged publish for all three packages at the current repository
  versions. The tag must equal `release-v` plus the package version, or the run fails early.

Every run publishes the same two distributions; there is no per-package publish path.

## Workflow behavior

1. Build all three packages with uv.
2. Run twine metadata checks.
3. Smoke-install the three produced wheels.
4. Assemble the payload and fail if either package is missing a wheel or sdist.
5. Publish all three packages to TestPyPI via trusted publishing.
6. Gate by installing all three packages from TestPyPI in a clean environment.
7. If the target is `both`, publish all three packages to PyPI after the gate succeeds. The PyPI upload runs
   `lkscaler-core` first, then `livekit-lkscaler`, then `lkscaler-keda`: if a project is missing its PyPI trusted
   publisher the run fails before anything is published, instead of leaving part of the set behind.

The version guard fails the run when `lkscaler-core`, `livekit-lkscaler` and `lkscaler-keda` do not share one version. The
TestPyPI install gate includes retries with backoff to tolerate index propagation delay.

## Prerequisites

- Trusted publishers, as of 2026-10-17: **TestPyPI is ready for all three** projects
  (`lkscaler-core`, `livekit-lkscaler`, `lkscaler-keda`). On **PyPI** only `livekit-lkscaler` has one, so the
  `both` target cannot upload `lkscaler-core` or `lkscaler-keda` until a pending/trusted publisher exists for
  each. A `testpypi` dispatch rehearses the whole coordinated flow without them.
- Versions must be bumped past anything already published to the target index. PyPI rejects re-uploads of an
  existing file, so publishing an unchanged version fails by design.

## Local preflight

Run before creating a release tag:

```bash
make milestone-gate
make release-verify
```

`make release-verify` builds all three distributions, enforces the shared version, asserts every wheel and sdist
exists, and smoke-installs them into a clean venv.

## Versioning

- Bump `lkscaler-core`, `livekit-lkscaler` and `lkscaler-keda` together, to the same version.
- Update CHANGELOG for release contents.
- Prefer semantic versioning: new packages/APIs are minor bumps while the project is pre-1.0.

## Staged release checklist

1. Run local preflight:

```bash
make release-preflight
```

2. Commit and push the version bump on `main`.

3. Trigger workflow_dispatch (GitHub UI or `gh workflow run publish.yml -f environment=testpypi`) and
   confirm the gate passes: all three packages publish to TestPyPI and the install gate job succeeds.

4. Trigger workflow_dispatch with `environment=both` when ready for production publish, or push the
   `release-vX.Y.Z` tag to run the staged flow in one go.

5. Optional local verification against TestPyPI:

```bash
make verify-testpypi-install PACKAGE=lkscaler-core VERSION=<version>
make verify-testpypi-install PACKAGE=livekit-lkscaler VERSION=<version>
```

## Current release policy

- Publishing all three packages together is the supported flow; per-package publishing is not.
- The Publish workflow runs `make proof-gate` in a blocking `proof-gate` job: `publish-testpypi` needs it and only
  runs when it succeeded, so no target publishes while any enforced scenario fails. The gate covers the unit,
  integration and compose E2E suites, the real-agent placement scenarios, the proof assertions and the KEDA
  scale proof in kind.
