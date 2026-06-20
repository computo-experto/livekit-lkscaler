# LiveKit KEDA Autoscaler Integration (Python) - Design Specification

**Date:** 2026-06-20
**Status:** Approved for planning
**Scope:** Kubernetes-native autoscaling integration for self-hosted LiveKit Agents that uses ZooKeeper state from the bin-pack library, KEDA for replica management, and kind for cluster-level testing.

## 1. Goal

Build a reusable repository component that turns the existing ZooKeeper occupancy data into a Kubernetes autoscaling loop for homogeneous LiveKit agent deployments.

Design target:

- Scale up when cluster free slots drop below a configurable threshold.
- Scale down only after free slots have stayed above the threshold for a configurable dwell period.
- Prefer deleting totally idle agent pods when scaling down.
- Validate the full autoscaling loop against a real Kubernetes cluster in CI.

## 2. Non-goals (v1)

- Replacing the existing bin-pack placement library.
- Autoscaling based on CPU, memory, or request rate instead of ZooKeeper occupancy.
- Cross-region placement or heterogeneous capacity weighting.
- Direct pod scheduling control beyond standard Kubernetes Deployment and KEDA behavior.

## 3. Assumptions

- The bin-pack library already records pod, room, and reservation state in ZooKeeper.
- LiveKit agent pods are homogeneous and run one agent process per pod.
- The Kubernetes workload is a Deployment or equivalent scalable controller with normal ReplicaSet behavior.
- KEDA is installed in the target cluster and can manage the workload scale subresource.
- The repository can run kind clusters in CI and locally.

## 4. Component Boundaries

### 4.1 `packages/lkscaler-keda`

New Python package that contains the KEDA-specific integration layer.

Responsibilities:

- Read ZooKeeper state produced by the bin-pack core package.
- Expose KEDA-compatible external metrics for cluster free slots and safe scale-down.
- Reconcile pod deletion cost annotations so Kubernetes prefers idle pods during scale-down.
- Provide manifests or helper templates for the KEDA ScaledObject, RBAC, and service wiring.

### 4.2 ZooKeeper state reuse

The KEDA integration does not own placement state. It consumes the same ZooKeeper data model used by the bin-pack library:

- `/pods/{pod_id}` for pod occupancy.
- `/rooms/{room_id}` for active rooms.
- `/reservations/{pod_id}/{job_id}` for reservations.

### 4.3 kind-based test harness

The autoscaler integration is verified in a real Kubernetes cluster created with kind.

Responsibilities:

- Install KEDA into the test cluster.
- Deploy a LiveKit agent workload and the autoscaler integration package.
- Exercise scale-up, dwell-based scale-down, and idle-pod deletion preference end to end.

## 5. Public Configuration Surface

`KedaAutoscalerConfig` (Pydantic):

- `namespace: str`
- `deployment_name: str`
- `zookeeper_hosts: list[str]`
- `min_cluster_free_slots: int`
- `scale_down_dwell_sec: int = 900`
- `poll_interval_sec: int = 15`
- `idle_pod_deletion_cost: int = 0`
- `busy_pod_deletion_cost: int = 100`
- `fail_closed_on_stale_snapshot: bool = True`

The free-slot threshold is cluster-wide and is independent from the per-pod room target used by the bin-pack library.

## 6. Autoscaling Policy

### 6.1 Cluster free-slot metric

The integration computes a cluster-wide free-slot metric from ZooKeeper by summing the `free_slots` values for all active pods.

Metric name:

- `cluster_free_slots`

Behavior:

- If `cluster_free_slots < min_cluster_free_slots`, KEDA should drive replica count up.
- If `cluster_free_slots >= min_cluster_free_slots`, the workload may remain steady or become eligible for scale-down.

### 6.2 Safe scale-down gate

Scale-down is only permitted when all of the following are true:

- `cluster_free_slots >= min_cluster_free_slots`.
- The cluster snapshot has remained above the threshold for at least `scale_down_dwell_sec`.
- There exists at least one totally idle pod, where totally idle means `active_rooms == 0` and `reservations == 0`.
- Removing the least-capacious idle pod would still leave the cluster at or above `min_cluster_free_slots`.

Metric name:

- `safe_remaining_free_slots_after_one_idle_removal`

Behavior:

- When scale-down is unsafe, the metric should stay at or above the target so the HPA does not reduce replicas.
- When scale-down is safe, the metric should drop below the target so the HPA can remove one replica.

This is the main guard that keeps scale-down from crossing back below the free-slot threshold.

### 6.3 Dwell time

The 15-minute dwell time requested by the user is modeled as a configurable default of `scale_down_dwell_sec = 900`.

Preferred implementation:

- Use KEDA/HPA scale-down stabilization behavior to hold the replica count steady while the metric fluctuates above threshold.
- Keep the metric gate conservative so scale-down is not allowed until the snapshot has remained healthy for the full dwell period.

### 6.4 Idle-pod preference

KEDA and HPA decide how many replicas should exist, but Kubernetes still chooses which pod to terminate.

To bias termination toward totally idle pods, the integration package maintains `controller.kubernetes.io/pod-deletion-cost` on agent pods:

- totally idle pods get `idle_pod_deletion_cost`
- pods with active rooms or reservations get `busy_pod_deletion_cost`

This lets the standard ReplicaSet scale-down path prefer an idle pod when one is available, without needing a custom pod-killer controller.

## 7. Data Flow

1. Agent pods publish occupancy into ZooKeeper through the bin-pack core library.
2. The KEDA integration reads the cached snapshot and computes cluster free slots.
3. The external metric service exposes the free-slot value and the safe scale-down gate.
4. KEDA/HPA scales the Deployment up or down based on those metrics.
5. The deletion-cost reconciler updates pod annotations so scale-down prefers totally idle pods.
6. The workload settles back into the bin-pack steady state.

## 8. Failure Handling

- **ZooKeeper unavailable or stale:** fail closed for scale-down by keeping the safe-down gate at or above target; scale-up should not be based on stale data.
- **KEDA service unavailable:** scaling remains frozen at the current replica count until the service recovers.
- **Deletion-cost reconciliation failure:** keep the scale-down gate conservative so the system does not terminate busy pods by mistake.
- **Kind cluster startup races:** use explicit readiness checks for KEDA, ZooKeeper, and the LiveKit workload before running assertions.

## 9. Testing Strategy

### 9.1 Unit tests

- Cluster free-slot aggregation from synthetic ZooKeeper snapshots.
- Safe-scale-down gate calculation with and without idle pods.
- Dwell-time gating behavior.
- Deletion-cost classification for idle versus busy pods.
- Fail-closed behavior when the snapshot is stale or unavailable.

### 9.2 Integration tests

- ZooKeeper-backed metric calculation against a test ensemble.
- KEDA metrics service responses for scale-up and scale-down cases.
- Deletion-cost annotations applied to live pod objects.

### 9.3 kind end-to-end tests

- Deploy a LiveKit agent workload, ZooKeeper, and KEDA into kind.
- Verify scale-up when free slots fall below threshold.
- Verify scale-down only after the dwell window elapses.
- Verify that a totally idle pod is the one most likely to be removed.
- Verify that removal does not take the cluster below the free-slot threshold.
- Verify ZooKeeper outage behavior remains conservative.

## 10. Acceptance Criteria

- The repository contains a KEDA integration package that consumes ZooKeeper state from the bin-pack library.
- The integration exposes cluster free slots and safe scale-down metrics suitable for KEDA.
- Scale-up occurs when free slots are below the configured threshold.
- Scale-down is blocked until the threshold has held for the configured dwell time.
- When scale-down occurs, Kubernetes prefers a totally idle pod.
- kind-based integration tests demonstrate the full loop in CI.

## 11. Deployment Constraints (v1)

- Supported development and CI cluster target is kind.
- The autoscaler component is intended for self-hosted LiveKit agents only.

## 12. Future Extension Points (post-v1)

- Prometheus export of the same ZooKeeper-derived metrics.
- More explicit pod ranking for scale-down beyond deletion cost.
- Weighted free-slot policies for heterogeneous deployments.