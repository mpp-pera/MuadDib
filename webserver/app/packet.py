import time
from pydantic import BaseModel, Field


class Packet(BaseModel):
    type: str
    device_id: str
    ts: float = Field(default_factory=time.time)
    payload: dict = Field(default_factory=dict)


def make_response(req: Packet, resp_type: str, payload: dict | None = None) -> Packet:
    return Packet(type=resp_type, device_id=req.device_id, payload=payload or {})


def error_packet(req: Packet, reason: str) -> Packet:
    return make_response(req, "error", {"reason": reason})
