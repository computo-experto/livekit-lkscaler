# lkscaler-keda

KEDA external scaler for LKScaler fleets: it answers KEDA's `ExternalScaler` gRPC contract from the same
coordination backend the workers use, so replicas follow how many slots your dispatch pattern actually needs.

## How it decides

The trigger reports one metric, `required_workers`:

```
required_workers = ceil((used_slots + minFreeSlots) / (roomTargetN + overflowMargin))
```

`used_slots` comes from the cluster snapshot in ZooKeeper or Redis (rooms plus live reservations per worker).
The ScaledObject's HPA target is `1`, so Kubernetes moves the deployment to exactly that many workers, bounded
by `minReplicaCount` and `maxReplicaCount`.

The scaler never asks for zero replicas. A pool with no workers cannot accept a dispatch, so one replica is
the floor and `IsActive` always answers true: KEDA's scale-to-zero path is deliberately unused. Set
`minReplicaCount: 1` and let `maxReplicaCount` bound the ceiling.

Headroom is expressed as a **number of slots** (`minFreeSlots`), not a percentage: it says how much admission
capacity must stay free for the burst pattern you expect. Provisioning that headroom is your capacity policy;
the scaler only holds the number you set. Do not expect a burst beyond it to be absorbed - see
`docs/usage/operations.md`.

Scale-down timing is KEDA's, not ours: set `pollingInterval`, `cooldownPeriod` and
`advanced.horizontalPodAutoscalerConfig.behavior.scaleDown.stabilizationWindowSeconds` to control how quickly
replicas come back down.

## ScaledObject

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: livekit-agents
  namespace: livekit-system
spec:
  scaleTargetRef:
    name: livekit-agents
  minReplicaCount: 1
  maxReplicaCount: 20
  pollingInterval: 15
  cooldownPeriod: 120
  triggers:
    - type: external
      metadata:
        scalerAddress: lkscaler-keda.livekit-system.svc.cluster.local:9090
        namespace: livekit-lkscaler
        backend: zookeeper
        zookeeperHosts: zk-0.zk:2181,zk-1.zk:2181,zk-2.zk:2181
        minFreeSlots: "8"
        roomTargetN: "2"
        overflowMargin: "1"
```

Metadata keys: `namespace`, `backend` (`zookeeper` or `redis`), `zookeeperHosts`, `redisUrl`,
`minFreeSlots`, `roomTargetN`, `overflowMargin`, `podStateTtlSec`.

## When the backend is unreachable

`GetMetrics` fails loudly instead of inventing a replica count. That is deliberate: KEDA's `fallback` block
is the standard answer - after `failureThreshold` consecutive failures it holds the deployment at
`fallback.replicas`:

```yaml
spec:
  fallback:
    failureThreshold: 3
    replicas: 2
```

A ZooKeeper ensemble or a managed Redis is very unlikely to go fully dark, and the case that does happen in
practice - one worker's pod state going stale - is already handled by the store TTL and needs no outage test.

## Run it

```bash
pip install "lkscaler-keda[zookeeper]"   # or [redis]
LKSCALER_KEDA_PORT=9090 lkscaler-keda-scaler
```

It speaks plaintext gRPC on that port; point `scalerAddress` at the Service in front of it.
