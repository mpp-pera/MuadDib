from . import database as db
from .packet import Packet, make_response, error_packet
from .registry import handler


@handler("register")
async def handle_register(pkt: Packet) -> Packet:
    payload = pkt.payload
    name = payload.get("name") or pkt.device_id
    device_type = payload.get("device_type", "")
    meta = {k: v for k, v in payload.items() if k not in ("name", "device_type")}
    db.upsert_device(pkt.device_id, name, device_type, meta)
    return make_response(pkt, "register_ack", {"status": "ok", "device_id": pkt.device_id})


@handler("heartbeat")
async def handle_heartbeat(pkt: Packet) -> Packet:
    if not db.update_heartbeat(pkt.device_id):
        return error_packet(pkt, "device not registered")
    return make_response(pkt, "heartbeat_ack")
