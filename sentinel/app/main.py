import asyncio
import html
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import database as db
from . import handlers  # noqa: F401 — registers all @handler decorators
from .packet import Packet
from .registry import dispatch
from .templates import render_page
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


@app.get("/device/{device_id}", include_in_schema=False)
async def device_page(device_id: str):
    row = db.get_device(device_id)
    if row is None:
        raise HTTPException(404, "device not found")
    d = dict(row)
    name = d["name"]
    meta = json.loads(d.get("meta") or "{}")
    ip = meta.get("ip")

    if ip:
        stream_url_js = json.dumps(f"http://{ip}:81/stream").replace("</", "<\\/")
        control_base_js = json.dumps(f"http://{ip}").replace("</", "<\\/")
        arrow_btn_classes = (
            "aspect-square flex items-center justify-center bg-gray-800 hover:bg-gray-700 "
            "active:bg-indigo-600 rounded-lg text-lg text-gray-300 transition-colors"
        )
        cam_feed = (
            '<section class="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">\n'
            '  <div class="px-6 py-4 border-b border-gray-800 flex items-center justify-between">\n'
            '    <h2 class="text-sm font-semibold text-gray-400 uppercase tracking-wider">Live Feed</h2>\n'
            '    <button id="cam-toggle-btn" onclick="toggleCamFeed()"\n'
            '      class="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium '
            'rounded-lg transition-colors">View cam feed</button>\n'
            '  </div>\n'
            '  <div id="cam-feed-placeholder" class="px-6 py-10 text-center text-sm text-gray-600">\n'
            '    Feed is off. Click &ldquo;View cam feed&rdquo; to start streaming.\n'
            '  </div>\n'
            '  <div id="cam-feed-body" class="hidden bg-black flex items-center justify-center">\n'
            '    <img id="cam-img" alt="Live camera feed" class="w-full max-h-[75vh] object-contain">\n'
            '  </div>\n'
            '</section>\n'
            '<section class="bg-gray-900 rounded-xl border border-gray-800 p-6">\n'
            '  <h2 class="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">Camera Control</h2>\n'
            '  <div class="grid grid-cols-3 gap-2 w-36 mx-auto">\n'
            '    <div></div>\n'
            f'    <button onclick="moveCam(\'up\')" class="{arrow_btn_classes}">&#9650;</button>\n'
            '    <div></div>\n'
            f'    <button onclick="moveCam(\'left\')" class="{arrow_btn_classes}">&#9664;</button>\n'
            '    <div></div>\n'
            f'    <button onclick="moveCam(\'right\')" class="{arrow_btn_classes}">&#9654;</button>\n'
            '    <div></div>\n'
            f'    <button onclick="moveCam(\'down\')" class="{arrow_btn_classes}">&#9660;</button>\n'
            '    <div></div>\n'
            '  </div>\n'
            '</section>\n'
            '<script>\n'
            '  (function () {\n'
            f'    const STREAM_URL = {stream_url_js};\n'
            f'    const CONTROL_BASE = {control_base_js};\n'
            '    let open = false;\n'
            '    window.toggleCamFeed = function () {\n'
            '      const img = document.getElementById("cam-img");\n'
            '      const body = document.getElementById("cam-feed-body");\n'
            '      const placeholder = document.getElementById("cam-feed-placeholder");\n'
            '      const btn = document.getElementById("cam-toggle-btn");\n'
            '      open = !open;\n'
            '      if (open) {\n'
            '        img.src = STREAM_URL;\n'
            '        body.classList.remove("hidden");\n'
            '        placeholder.classList.add("hidden");\n'
            '        btn.textContent = "Close feed";\n'
            '      } else {\n'
            '        img.src = "";\n'
            '        body.classList.add("hidden");\n'
            '        placeholder.classList.remove("hidden");\n'
            '        btn.textContent = "View cam feed";\n'
            '      }\n'
            '    };\n'
            '    window.moveCam = function (dir) {\n'
            '      fetch(CONTROL_BASE + "/servo?dir=" + dir).catch(() => {});\n'
            '    };\n'
            '  })();\n'
            '</script>'
        )
    else:
        cam_feed = (
            '<section class="bg-gray-900 rounded-xl border border-gray-800 p-6">\n'
            '  <h2 class="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">Live Feed</h2>\n'
            '  <p class="text-sm text-gray-500">Cam feed unavailable (no heartbeat received yet)</p>\n'
            '</section>'
        )

    body = (
        '<section class="bg-gray-900 rounded-xl border border-gray-800 p-6">\n'
        f'  <p class="text-gray-100">This is the page for {html.escape(name)}</p>\n'
        '</section>\n'
        f'{cam_feed}'
    )
    return HTMLResponse(render_page(name, body))


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
