from typing import Literal

from pydantic import BaseModel, Field


class BinpackConfig(BaseModel):
    namespace: str
    pod_id: str
    room_target_n: int = Field(ge=1)
    overflow_margin: int = Field(default=1, ge=0)
    reservation_ttl_sec: int = Field(gt=0)
    zk_session_timeout_sec: int = Field(gt=0)
    sync_interval_ms: int = Field(gt=0)
    fail_mode: Literal["accept_if_local_below_n"] = "accept_if_local_below_n"
