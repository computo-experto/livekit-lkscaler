# Release Guide

This guide covers package release flow for lkscaler-core and livekit-lkscaler.

## Release triggers

- Manual: run the Publish workflow via workflow_dispatch and choose package plus target.
- Tag-based: push a tag and let workflow infer package automatically:
  - lkscaler-core-vX.Y.Z
  - livekit-lkscaler-vX.Y.Z

Tag-based releases default to staged publish (TestPyPI then PyPI).

## Workflow behavior

1. Build selected package with uv.
2. Run twine metadata checks.
3. Smoke-install produced wheel.
4. Upload dist artifacts.
5. Publish to TestPyPI and/or PyPI via trusted publishing.

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
  - package: `lkscaler-core`
  - environment: `testpypi`

3. Validate TestPyPI install:

```bash
make verify-testpypi-install PACKAGE=lkscaler-core VERSION=<version>
```

4. Repeat for adapter package:
  - package: `livekit-lkscaler`
  - environment: `testpypi`

```bash
make verify-testpypi-install PACKAGE=livekit-lkscaler VERSION=<version>
```

5. After both succeed on TestPyPI, run publish workflow for `pypi` or `both`.
