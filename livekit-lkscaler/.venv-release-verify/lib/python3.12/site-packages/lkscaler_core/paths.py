def _validate_segment(value: str, *, name: str) -> str:
    trimmed = value.strip()
    if not trimmed:
        raise ValueError(f"{name} cannot be empty")
    if "/" in trimmed:
        raise ValueError(f"{name} cannot contain '/'")
    return trimmed


class ZkPaths:
    """Path helper for the LKScaler ZooKeeper data model."""

    def __init__(self, namespace: str) -> None:
        namespace = _validate_segment(namespace, name="namespace")
        self._base = f"/livekit-binpack/{namespace}"

    @property
    def base(self) -> str:
        return self._base

    def pod_node(self, pod_id: str) -> str:
        pod_id = _validate_segment(pod_id, name="pod_id")
        return f"{self._base}/pods/{pod_id}"

    def room_node(self, room_id: str) -> str:
        room_id = _validate_segment(room_id, name="room_id")
        return f"{self._base}/rooms/{room_id}"

    def reservation_parent(self, pod_id: str) -> str:
        pod_id = _validate_segment(pod_id, name="pod_id")
        return f"{self._base}/reservations/{pod_id}"

    def reservation_node(self, pod_id: str, job_id: str) -> str:
        pod_id = _validate_segment(pod_id, name="pod_id")
        job_id = _validate_segment(job_id, name="job_id")
        return f"{self._base}/reservations/{pod_id}/{job_id}"
