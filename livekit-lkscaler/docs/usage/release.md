# Release Guide

This guide covers the coordinated release flow for `lkscaler-core` and `livekit-lkscaler`. Both packages
always ship together at one shared version.

## Release triggers

- Manual: run the Publish workflow via workflow_dispatch and choose target (`testpypi` or `both`).
- Tag-based: push `release-vX.Y.Z` to run the staged publish for both packages at the current repository
  versions. The tag must equal `release-v` plus the package version, or the run fails early.

Every run publishes the same two distributions; there is no per-package publish path.

## Workflow behavior

1. Build both packages with uv.
2. Run twine metadata checks.
3. Smoke-install both produced wheels.
4. Assemble the payload and fail if either package is missing a wheel or sdist.
5. Publish both packages to TestPyPI via trusted publishing.
6. Gate by installing both packages from TestPyPI in a clean environment.
7. If the target is `both`, publish both packages to PyPI after the gate succeeds. The PyPI upload is split
   into two ordered steps, `lkscaler-core` first: if a project is missing its PyPI trusted publisher the run
   fails before anything is published, instead of leaving one package of the pair behind.

The version guard fails the run when `lkscaler-core` and `livekit-lkscaler` do not share one version. The
TestPyPI install gate includes retries with backoff to tolerate index propagation delay.

## Prerequisites

- PyPI trusted publishers must exist for **both** projects. `livekit-lkscaler` has one; `lkscaler-core`
  additionally requires a pending publisher on PyPI (or the matching trusted publisher) before the PyPI
  stage can upload it. TestPyPI already has both.
- Versions must be bumped past anything already published to the target index. PyPI rejects re-uploads of an
  existing file, so publishing an unchanged version fails by design.

## Local preflight

Run before creating a release tag:

```bash
make milestone-gate
make release-verify
```

`make release-verify` builds both distributions, enforces the shared version, asserts both wheels and sdists
exist, and smoke-installs both into a clean venv.

## Versioning

- Bump `lkscaler-core` and `livekit-lkscaler` together, to the same version.
- Update CHANGELOG for release contents.
- Prefer semantic versioning: new packages/APIs are minor bumps while the project is pre-1.0.

## Staged release checklist

1. Run local preflight:

```bash
make release-preflight
```

2. Commit and push the version bump on `main`.

3. Trigger workflow_dispatch (GitHub UI or `gh workflow run publish.yml -f environment=testpypi`) and
   confirm the gate passes: both packages publish to TestPyPI and the install gate job succeeds.

4. Trigger workflow_dispatch with `environment=both` when ready for production publish, or push the
   `release-vX.Y.Z` tag to run the staged flow in one go.

5. Optional local verification against TestPyPI:

```bash
make verify-testpypi-install PACKAGE=lkscaler-core VERSION=<version>
make verify-testpypi-install PACKAGE=livekit-lkscaler VERSION=<version>
```

## Current release policy

- Publishing both packages together is the supported flow; per-package publishing is not.
- The Milestone 9 proof gate (`make proof-gate`) is the documented real-world integration gate, but it is not
  yet wired as an automated release block. Treat it as a manual pre-release check, and do not describe the
  release as proof-gated until the workflow enforces it.
