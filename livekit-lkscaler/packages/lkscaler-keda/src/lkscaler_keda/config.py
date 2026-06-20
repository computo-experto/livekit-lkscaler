from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class KedaAutoscalerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    namespace: str = Field(..., description="Kubernetes namespace")
    deployment_name: str = Field(..., description="Name of the agent deployment")
    zookeeper_hosts: list[str] = Field(..., min_length=1, description="ZooKeeper host:port list")
    min_cluster_free_slots: int = Field(..., ge=0, description="Minimum free slots to maintain")
    scale_down_dwell_sec: int = Field(default=900, gt=0)
    poll_interval_sec: int = Field(default=15, gt=0)
    idle_pod_deletion_cost: int = Field(default=0, ge=0)
    busy_pod_deletion_cost: int = Field(default=100, ge=0)
    fail_closed_on_stale_snapshot: bool = Field(default=True)

    @field_validator("zookeeper_hosts")
    @classmethod
    def _validate_zookeeper_hosts(cls, value: list[str]) -> list[str]:
        if any(not host.strip() for host in value):
            raise ValueError("zookeeper_hosts entries must be non-empty")
        return value

    @model_validator(mode="after")
    def _validate_deletion_cost_ordering(self) -> "KedaAutoscalerConfig":
        if self.busy_pod_deletion_cost < self.idle_pod_deletion_cost:
            raise ValueError("busy_pod_deletion_cost must be >= idle_pod_deletion_cost")
        return self