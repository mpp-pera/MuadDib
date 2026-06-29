import asyncio
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import database as db
from . import handlers  # noqa: F401 — registers all @handler decorators
from .packet import Packet
from .registry import dispatch
from .ws_manager import manager

STATIC_DIR = Path(__file__).parent / "static"


async def _offline_checker() -> None:
    while True:
        await asyncio.sleep(60)
        stale = db.mark_stale_offline(max_age_s=120)
        if stale:
            print(f"[hub] marked {stale} device(s) offline (no heartbeat >120s)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    task = asyncio.create_task(_offline_checker())
    yield
    task.cancel()


app = FastAPI(title="IoT Hub", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# --- dashboard ---

@app.get("/", include_in_schema=False)
async def dashboard():
    return FileResponse(STATIC_DIR / "index.html")


# --- device REST ---

@app.get("/api/devices")
async def list_devices():
    rows = db.list_devices()
    return [_row_to_dict(r) for r in rows]


@app.get("/api/devices/{device_id}")
async def get_device(device_id: str):
    row = db.get_device(device_id)
    if row is None:
        raise HTTPException(404, "device not found")
    return _row_to_dict(row)


@app.delete("/api/devices/{device_id}", status_code=204)
async def delete_device(device_id: str):
    if not db.delete_device(device_id):
        raise HTTPException(404, "device not found")
    manager.disconnect(device_id)


# --- unified message endpoint (HTTP) ---

@app.post("/api/message")
async def http_message(pkt: Packet):
    resp = await dispatch(pkt)
    return resp.model_dump()


# --- WebSocket endpoint ---

@app.websocket("/ws/{device_id}")
async def ws_endpoint(ws: WebSocket, device_id: str):
    row = db.get_device(device_id)
    if row is None:
        await ws.close(code=4001, reason="device not registered")
        return

    await manager.connect(device_id, ws)
    db.update_heartbeat(device_id)
    print(f"[hub] {device_id} connected via WebSocket")

    try:
        while True:
            text = await ws.receive_text()
            try:
                pkt = Packet.model_validate_json(text)
            except Exception:
                await ws.send_text(json.dumps({"type": "error", "device_id": device_id,
                                               "ts": time.time(), "payload": {"reason": "invalid packet"}}))
                continue
            resp = await dispatch(pkt)
            await ws.send_text(resp.model_dump_json())
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(device_id)
        db.set_device_offline(device_id)
        print(f"[hub] {device_id} disconnected")


# --- helpers ---

def _row_to_dict(row) -> dict:
    d = dict(row)
    d["meta"] = json.loads(d.get("meta") or "{}")
    d["connected"] = manager.is_connected(d["id"])
    return d
