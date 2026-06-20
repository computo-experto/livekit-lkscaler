# Release Guide

This guide covers coordinated release flow for lkscaler-core and livekit-lkscaler.

## Release triggers

- Manual: run the Publish workflow via workflow_dispatch and choose target (`testpypi` or `both`).
- Tag-based: push `release-vX.Y.Z` to run staged publish for both packages at current repository versions.

## Workflow behavior

1. Build both packages with uv.
2. Run twine metadata checks.
3. Smoke-install both produced wheels.
4. Upload dist artifacts.
5. Publish both packages to TestPyPI via trusted publishing.
6. Run gate by installing both packages from TestPyPI in a clean environment.
7. If target is `both`, publish both packages to PyPI.

The TestPyPI install gate includes retries with backoff to tolerate index propagation delay.

## Local preflight

Run before creating a release tag:

```bash
make milestone-gate
make release-verify
```

## Versioning

- Keep semantic versioning in package pyproject files.
- Update CHANGELOG for release contents.
- For first external release, prefer workflow_dispatch with testpypi target.

## Milestone 8 checklist (external publish validation)

1. Run local preflight:

```bash
make release-preflight
```

2. Trigger workflow_dispatch (GitHub UI):
  - workflow: `Publish`
  - environment: `testpypi`

3. Confirm workflow gate passes:
  - both packages publish to TestPyPI.
  - TestPyPI install gate job succeeds.

4. Trigger workflow_dispatch again with `environment=both` when ready for production publish.

5. Optional local verification against TestPyPI:

```bash
make verify-testpypi-install PACKAGE=lkscaler-core VERSION=<version>
make verify-testpypi-install PACKAGE=livekit-lkscaler VERSION=<version>
```
