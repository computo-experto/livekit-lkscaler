# LiveKit KEDA Autoscaler Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a KEDA-backed autoscaling integration that reads ZooKeeper occupancy from the existing bin-pack library, scales LiveKit agent Deployments up when free slots are low, and scales down only after a dwell period while preferring totally idle pods.

**Architecture:** Reuse the existing ZooKeeper state model in `lkscaler-core`, add a new `lkscaler-keda` package that computes cluster-wide free slots and exposes a KEDA external scaler, and keep pod termination bias in a small Kubernetes reconciler that stamps pod deletion cost. Use kind for the Kubernetes execution path so the autoscaler runs against a real cluster API, while the existing Docker Compose assets remain for non-Kubernetes service tests.

**Tech Stack:** Python 3.12, uv workspace, Pydantic, kazoo, grpcio, grpcio-tools, Kubernetes Python client, KEDA, kind, pytest, ruff, mypy.

---

## 1. File Map

### New package

- Create: `livekit-lkscaler/packages/lkscaler-keda/pyproject.toml`
- Create: `livekit-lkscaler/packages/lkscaler-keda/src/lkscaler_keda/__init__.py`
- Create: `livekit-lkscaler/packages/lkscaler-keda/src/lkscaler_keda/config.py`
- Create: `livekit-lkscaler/packages/lkscaler-keda/src/lkscaler_keda/snapshot.py`
- Create: `livekit-lkscaler/packages/lkscaler-keda/src/lkscaler_keda/policy.py`
- Create: `livekit-lkscaler/packages/lkscaler-keda/src/lkscaler_keda/scaler.py`
- Create: `livekit-lkscaler/packages/lkscaler-keda/src/lkscaler_keda/deletion_cost.py`
- Create: `livekit-lkscaler/packages/lkscaler-keda/src/lkscaler_keda/manifests/scaledobject.yaml`
- Create: `livekit-lkscaler/packages/lkscaler-keda/src/lkscaler_keda/manifests/rbac.yaml`
- Create: `livekit-lkscaler/packages/lkscaler-keda/src/lkscaler_keda/proto/externalscaler.proto`
- Create: `livekit-lkscaler/packages/lkscaler-keda/tests/unit/test_config.py`
- Create: `livekit-lkscaler/packages/lkscaler-keda/tests/unit/test_snapshot.py`
- Create: `livekit-lkscaler/packages/lkscaler-keda/tests/unit/test_policy.py`
- Create: `livekit-lkscaler/packages/lkscaler-keda/tests/unit/test_deletion_cost.py`
- Create: `livekit-lkscaler/packages/lkscaler-keda/tests/integration/test_external_scaler.py`
- Create: `livekit-lkscaler/packages/lkscaler-keda/tests/integration/test_k8s_reconciler.py`

### Existing files to modify

- Modify: `livekit-lkscaler/pyproject.toml`
- Modify: `livekit-lkscaler/packages/lkscaler-core/src/lkscaler_core/snapshot.py`
- Modify: `livekit-lkscaler/packages/lkscaler-core/tests/unit/test_snapshot.py`
- Modify: `livekit-lkscaler/e2e/pyproject.toml`
- Modify: `livekit-lkscaler/e2e/tests/test_e2e_binpack.py` or add a new KEDA-focused e2e test file alongside it
- Modify: `livekit-lkscaler/Makefile`
- Modify: `livekit-lkscaler/scripts/run_e2e.sh` or add a new `run_keda_e2e.sh`
- Modify: `livekit-lkscaler/.github/workflows/ci.yml`
- Modify: `livekit-lkscaler/docs/usage/integration.md`
- Modify: `livekit-lkscaler/docs/usage/operations.md`
- Modify: `livekit-lkscaler/docs/usage/testing.md`
- Modify: `livekit-lkscaler/README.md`

---

## 2. Task 1: Package Scaffold and Shared Snapshot Summary

**Files:**
- Create: `livekit-lkscaler/packages/lkscaler-keda/pyproject.toml`
- Create: `livekit-lkscaler/packages/lkscaler-keda/src/lkscaler_keda/__init__.py`
- Create: `livekit-lkscaler/packages/lkscaler-keda/src/lkscaler_keda/config.py`
- Create: `livekit-lkscaler/packages/lkscaler-keda/src/lkscaler_keda/snapshot.py`
- Modify: `livekit-lkscaler/packages/lkscaler-core/src/lkscaler_core/snapshot.py`
- Modify: `livekit-lkscaler/pyproject.toml`
- Test: `livekit-lkscaler/packages/lkscaler-keda/tests/unit/test_config.py`
- Test: `livekit-lkscaler/packages/lkscaler-core/tests/unit/test_snapshot.py`

- [ ] **Step 1: Write the failing tests**

Add a config test that asserts the defaults and required fields:

```python
def test_keda_autoscaler_config_defaults():
    config = KedaAutoscalerConfig(namespace="livekit", deployment_name="agents", zookeeper_hosts=["zk:2181"], min_cluster_free_slots=4)

    assert config.scale_down_dwell_sec == 900
    assert config.poll_interval_sec == 15
    assert config.idle_pod_deletion_cost == 0
    assert config.busy_pod_deletion_cost == 100
```

Add a snapshot summary test that feeds synthetic pod states into the existing core snapshot model and checks the cluster totals:

```python
def test_cluster_snapshot_summary_counts_free_slots_and_idle_pods():
    summary = summarize_cluster_snapshot(
        pods=[
            PodSnapshot(pod_id="pod-a", active_rooms=2, reservations=1, room_target_n=4),
            PodSnapshot(pod_id="pod-b", active_rooms=0, reservations=0, room_target_n=4),
        ],
        snapshot_at=1700000000,
        observed_at=1700000030,
    )

    assert summary.cluster_free_slots == 5
    assert summary.idle_pod_count == 1
    assert summary.snapshot_age_sec == 30
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest packages/lkscaler-keda/tests/unit/test_config.py packages/lkscaler-core/tests/unit/test_snapshot.py -q`

Expected: fail because the new package and the shared summary helper do not exist yet.

- [ ] **Step 3: Write the minimal implementation**

Implement `KedaAutoscalerConfig` in `config.py`, add a cluster snapshot summary helper in `lkscaler_core.snapshot`, and expose a small `ClusterSnapshotSummary` model from the KEDA package so the later policy code can consume the same shape everywhere.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest packages/lkscaler-keda/tests/unit/test_config.py packages/lkscaler-core/tests/unit/test_snapshot.py -q`

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add livekit-lkscaler/pyproject.toml \
  livekit-lkscaler/packages/lkscaler-core/src/lkscaler_core/snapshot.py \
  livekit-lkscaler/packages/lkscaler-core/tests/unit/test_snapshot.py \
  livekit-lkscaler/packages/lkscaler-keda
git commit -m "feat: scaffold keda autoscaler package"
```

## 3. Task 2: Free-Slot Policy and KEDA External Scaler

**Files:**
- Create: `livekit-lkscaler/packages/lkscaler-keda/src/lkscaler_keda/policy.py`
- Create: `livekit-lkscaler/packages/lkscaler-keda/src/lkscaler_keda/scaler.py`
- Create: `livekit-lkscaler/packages/lkscaler-keda/src/lkscaler_keda/proto/externalscaler.proto`
- Create: `livekit-lkscaler/packages/lkscaler-keda/tests/unit/test_policy.py`
- Create: `livekit-lkscaler/packages/lkscaler-keda/tests/integration/test_external_scaler.py`

- [ ] **Step 1: Write the failing tests**

Add a policy test that proves the scale-down gate only opens when the cluster is above the threshold, the snapshot has aged for the dwell period, and at least one totally idle pod can be removed without dropping below the threshold:

```python
def test_safe_scale_down_requires_threshold_dwell_and_idle_pod():
    policy = AutoscalerPolicy(min_cluster_free_slots=4, scale_down_dwell_sec=900)

    result = policy.evaluate(
        summary=ClusterSnapshotSummary(cluster_free_slots=5, idle_pod_count=1, snapshot_age_sec=901, smallest_idle_pod_free_slots=1),
    )

    assert result.scale_up == False
    assert result.scale_down_allowed == True
```

Add an external scaler test that checks the metric names and values returned to KEDA:

```python
def test_external_scaler_reports_cluster_free_slots_metric():
    metrics = scaler.get_metrics("cluster_free_slots")
    assert metrics[0].metricName == "cluster_free_slots"
    assert metrics[0].metricValue == "5"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest packages/lkscaler-keda/tests/unit/test_policy.py packages/lkscaler-keda/tests/integration/test_external_scaler.py -q`

Expected: fail because the policy and scaler classes are not implemented yet.

- [ ] **Step 3: Write the minimal implementation**

Implement `AutoscalerPolicy` in `policy.py` and the KEDA external scaler service in `scaler.py`. Keep the metric behavior simple and explicit: `cluster_free_slots` is the cluster-wide gauge, and the scale-down gate only opens when the dwell window and idle-pod conditions are both true.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest packages/lkscaler-keda/tests/unit/test_policy.py packages/lkscaler-keda/tests/integration/test_external_scaler.py -q`

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add livekit-lkscaler/packages/lkscaler-keda/src/lkscaler_keda/policy.py \
  livekit-lkscaler/packages/lkscaler-keda/src/lkscaler_keda/scaler.py \
  livekit-lkscaler/packages/lkscaler-keda/src/lkscaler_keda/proto/externalscaler.proto \
  livekit-lkscaler/packages/lkscaler-keda/tests/unit/test_policy.py \
  livekit-lkscaler/packages/lkscaler-keda/tests/integration/test_external_scaler.py
git commit -m "feat: add keda free-slot policy"
```

## 4. Task 3: Pod Deletion Cost Reconciler and Kubernetes Manifests

**Files:**
- Create: `livekit-lkscaler/packages/lkscaler-keda/src/lkscaler_keda/deletion_cost.py`
- Create: `livekit-lkscaler/packages/lkscaler-keda/src/lkscaler_keda/manifests/scaledobject.yaml`
- Create: `livekit-lkscaler/packages/lkscaler-keda/src/lkscaler_keda/manifests/rbac.yaml`
- Create: `livekit-lkscaler/packages/lkscaler-keda/tests/unit/test_deletion_cost.py`
- Create: `livekit-lkscaler/packages/lkscaler-keda/tests/integration/test_k8s_reconciler.py`

- [ ] **Step 1: Write the failing tests**

Add a deletion-cost test that maps idle and busy pods to the configured costs:

```python
def test_idle_pods_get_lower_deletion_cost():
    assert choose_deletion_cost(active_rooms=0, reservations=0, idle_cost=0, busy_cost=100) == 0
    assert choose_deletion_cost(active_rooms=1, reservations=0, idle_cost=0, busy_cost=100) == 100
```

Add a reconciler test that checks the pod annotation is patched to `controller.kubernetes.io/pod-deletion-cost` for both pod states.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest packages/lkscaler-keda/tests/unit/test_deletion_cost.py packages/lkscaler-keda/tests/integration/test_k8s_reconciler.py -q`

Expected: fail because the reconciler and manifest helpers do not exist yet.

- [ ] **Step 3: Write the minimal implementation**

Implement the deletion-cost selector and a small Kubernetes client wrapper that patches the live pod annotation. Add the ScaledObject and RBAC manifests so the KEDA service can read ZooKeeper state and update pod metadata.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest packages/lkscaler-keda/tests/unit/test_deletion_cost.py packages/lkscaler-keda/tests/integration/test_k8s_reconciler.py -q`

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add livekit-lkscaler/packages/lkscaler-keda/src/lkscaler_keda/deletion_cost.py \
  livekit-lkscaler/packages/lkscaler-keda/src/lkscaler_keda/manifests/scaledobject.yaml \
  livekit-lkscaler/packages/lkscaler-keda/src/lkscaler_keda/manifests/rbac.yaml \
  livekit-lkscaler/packages/lkscaler-keda/tests/unit/test_deletion_cost.py \
  livekit-lkscaler/packages/lkscaler-keda/tests/integration/test_k8s_reconciler.py
git commit -m "feat: bias keda scale-down toward idle pods"
```

## 5. Task 4: kind-Based End-to-End Harness

**Files:**
- Create: `livekit-lkscaler/e2e/kind/kind-config.yaml`
- Create: `livekit-lkscaler/e2e/kind/install_keda.sh`
- Create: `livekit-lkscaler/e2e/tests/test_keda_e2e.py`
- Modify: `livekit-lkscaler/e2e/pyproject.toml`
- Modify: `livekit-lkscaler/Makefile`
- Modify: `livekit-lkscaler/scripts/run_e2e.sh` or create `livekit-lkscaler/scripts/run_keda_e2e.sh`

- [ ] **Step 1: Write the failing e2e test**

Add an e2e test that creates the kind cluster, installs KEDA, deploys ZooKeeper and the LiveKit agent workload, then asserts the replica count rises when `cluster_free_slots` drops below the configured threshold and falls only after the dwell window has elapsed.

```python
def test_keda_scales_up_then_scales_down_after_dwell():
    assert wait_for_replicas("agents", 2)
    assert wait_for_metric("cluster_free_slots", below=4)
    assert wait_for_replicas("agents", 3)
    assert wait_for_metric("cluster_free_slots", above=4, stable_for_seconds=900)
    assert wait_for_replicas("agents", 2)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest e2e/tests/test_keda_e2e.py -q`

Expected: fail because the kind harness and KEDA deployment assets do not exist yet.

- [ ] **Step 3: Write the minimal harness**

Implement the kind cluster config, install script, and a test fixture that loads the KEDA manifests and waits for the controller, metrics service, ZooKeeper, and agent pods to become ready before assertions start.

- [ ] **Step 4: Run the e2e test to verify it passes**

Run: `uv run pytest e2e/tests/test_keda_e2e.py -q`

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add livekit-lkscaler/e2e/kind/kind-config.yaml \
  livekit-lkscaler/e2e/kind/install_keda.sh \
  livekit-lkscaler/e2e/tests/test_keda_e2e.py \
  livekit-lkscaler/e2e/pyproject.toml \
  livekit-lkscaler/Makefile \
  livekit-lkscaler/scripts/run_e2e.sh
git commit -m "feat: add kind e2e coverage for keda autoscaling"
```

## 6. Task 5: Docs, CI, and Final Validation

**Files:**
- Modify: `livekit-lkscaler/docs/usage/integration.md`
- Modify: `livekit-lkscaler/docs/usage/operations.md`
- Modify: `livekit-lkscaler/docs/usage/testing.md`
- Modify: `livekit-lkscaler/README.md`
- Modify: `livekit-lkscaler/.github/workflows/ci.yml`

- [ ] **Step 1: Write the documentation and CI checks**

Document the KEDA config knobs, the dwell-time policy, the pod-deletion-cost behavior, and the new kind-based e2e command. Add a CI job that runs the new unit, integration, and kind e2e checks without dropping the existing bin-pack coverage.

- [ ] **Step 2: Run the repository-level validation**

Run: `make -C livekit-lkscaler milestone-gate`

Expected: pass once the KEDA package, kind harness, and CI wiring are complete.

- [ ] **Step 3: Commit**

```bash
git add livekit-lkscaler/docs/usage/integration.md \
  livekit-lkscaler/docs/usage/operations.md \
  livekit-lkscaler/docs/usage/testing.md \
  livekit-lkscaler/README.md \
  livekit-lkscaler/.github/workflows/ci.yml
git commit -m "docs: add keda autoscaling workflow"
```

---

## 7. Self-Review Checklist

- The KEDA package has concrete files for config, policy, scaler, deletion cost, and manifests.
- The plan covers the ZooKeeper-derived free-slot metric and the dwell-based scale-down gate from the spec.
- The plan includes idle-pod preference through `controller.kubernetes.io/pod-deletion-cost`.
- The plan switches the KEDA execution path to kind and leaves k3s out entirely.
- The plan updates docs, CI, and repository-level validation after the code work lands.
