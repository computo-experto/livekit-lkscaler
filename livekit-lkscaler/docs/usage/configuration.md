# Configuration

`BinpackConfig` controls admission, overflow safety, and synchronization behavior.

For a consumer-oriented explanation of which settings matter and how to start, see [Library User Guide](library-users.md).

## Fields LKScaler reads

These change admission, packing, or the load signal the server selects on:

- `namespace` (`str`): logical namespace used for cluster state partitioning.
- `pod_id` (`str`): unique identifier for the current worker pod.
- `room_target_n` (`int`, `>= 1`): target concurrent rooms per pod.
- `overflow_margin` (`int`, `>= 0`): extra slots tolerated during race windows.
- `reservation_ttl_sec` (`int`, `> 0`): reservation timeout managed by the parent process.

## Declarations for the coordination layer you supply

These are validated and carried, never read. Changing them does not change admission, packing, or the load
signal - they exist so one config object also carries what your store and tracker need:

- `zk_session_timeout_sec` (`int`, `> 0`): session timeout for a ZooKeeper-backed store.
- `sync_interval_ms` (`int`, `> 0`): snapshot refresh interval for a polling tracker.
- `fail_mode` (`Literal["accept_if_local_below_n"]`): fallback strategy when cluster state is unavailable.

Read them from the same `BinpackConfig` in your own store or tracker instead of duplicating configuration. The
shipped `ZooKeeperStateStore`, `RedisStateStore` and the LiveKit hooks take their timeouts from their own
constructors, so nothing here silently changes their behaviour.

## Recommended starting values

```python
BinpackConfig(
	namespace="livekit-lkscaler",
	pod_id="worker-1",
	room_target_n=2,
	overflow_margin=1,
	reservation_ttl_sec=30,
	zk_session_timeout_sec=10,
	sync_interval_ms=250,
)
```

## Sizing guidance

- Start with `room_target_n` equal to known safe concurrency per worker.
- Keep `overflow_margin` small (usually `1`) to cap race-induced oversubscription.
- Keep `reservation_ttl_sec` long enough for normal accept-to-assignment delay, but short enough to remove stale reservations quickly.
