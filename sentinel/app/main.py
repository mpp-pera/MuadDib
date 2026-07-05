import asyncio
import html
import json
import queue
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import database as db
from . import handlers  # noqa: F401 — registers all @handler decorators
from . import streaming
from . import vision
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
        stream_url_js = json.dumps(f"/api/devices/{device_id}/stream").replace("</", "<\\/")
        control_base_js = json.dumps(f"http://{ip}").replace("</", "<\\/")
        device_id_js = json.dumps(device_id).replace("</", "<\\/")
        arrow_btn_classes = (
            "aspect-square flex items-center justify-center bg-gray-800 hover:bg-gray-700 "
            "active:bg-indigo-600 rounded-lg text-lg text-gray-300 transition-colors"
        )
        cam_feed = (
            '<section class="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">\n'
            '  <div class="px-6 py-4 border-b border-gray-800 flex items-center justify-between">\n'
            '    <h2 class="text-sm font-semibold text-gray-400 uppercase tracking-wider">Live Feed</h2>\n'
            '    <div class="flex gap-2">\n'
            '      <button id="tag-toggle-btn" onclick="toggleTagging()"\n'
            '        class="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-200 text-xs font-medium '
            'rounded-lg transition-colors">Tag objects</button>\n'
            '      <button id="cam-toggle-btn" onclick="toggleCamFeed()"\n'
            '        class="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium '
            'rounded-lg transition-colors">View cam feed</button>\n'
            '    </div>\n'
            '  </div>\n'
            '  <div id="cam-feed-placeholder" class="px-6 py-10 text-center text-sm text-gray-600">\n'
            '    Feed is off. Click &ldquo;View cam feed&rdquo; to start streaming.\n'
            '  </div>\n'
            '  <div id="cam-feed-body" class="hidden bg-black relative flex items-center justify-center">\n'
            '    <img id="cam-img" alt="Live camera feed" class="w-full max-h-[75vh] object-contain">\n'
            '    <canvas id="cam-canvas" class="absolute inset-0 w-full h-full pointer-events-none"></canvas>\n'
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
            f'    const DEVICE_ID = {device_id_js};\n'
            '    let open = false;\n'
            '    let tagging = false;\n'
            '    let tagPollTimer = null;\n'
            '\n'
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
            '        if (tagging) toggleTagging();\n'
            '      }\n'
            '    };\n'
            '\n'
            '    window.moveCam = function (dir) {\n'
            '      fetch(CONTROL_BASE + "/servo?dir=" + dir).catch(() => {});\n'
            '    };\n'
            '\n'
            '    window.toggleTagging = function () {\n'
            '      const btn = document.getElementById("tag-toggle-btn");\n'
            '      tagging = !tagging;\n'
            '      if (tagging) {\n'
            '        if (!open) toggleCamFeed();\n'
            '        btn.textContent = "Stop tagging";\n'
            '        btn.classList.add("bg-emerald-600", "hover:bg-emerald-500", "text-white");\n'
            '        btn.classList.remove("bg-gray-800", "hover:bg-gray-700", "text-gray-200");\n'
            '        setTagging(true);\n'
            '        tagPollTimer = setInterval(pollTags, 400);\n'
            '      } else {\n'
            '        btn.textContent = "Tag objects";\n'
            '        btn.classList.remove("bg-emerald-600", "hover:bg-emerald-500", "text-white");\n'
            '        btn.classList.add("bg-gray-800", "hover:bg-gray-700", "text-gray-200");\n'
            '        setTagging(false);\n'
            '        clearInterval(tagPollTimer);\n'
            '        tagPollTimer = null;\n'
            '        clearCanvas();\n'
            '      }\n'
            '    };\n'
            '\n'
            '    function setTagging(enabled) {\n'
            '      fetch(`/api/devices/${DEVICE_ID}/tagging`, {\n'
            '        method: "POST", headers: {"Content-Type": "application/json"},\n'
            '        body: JSON.stringify({enabled}),\n'
            '      }).catch(() => {});\n'
            '    }\n'
            '\n'
            '    function clearCanvas() {\n'
            '      const canvas = document.getElementById("cam-canvas");\n'
            '      canvas.getContext("2d").clearRect(0, 0, canvas.width, canvas.height);\n'
            '    }\n'
            '\n'
            '    async function pollTags() {\n'
            '      try {\n'
            '        const res = await fetch(`/api/devices/${DEVICE_ID}/tags`);\n'
            '        drawTags(await res.json());\n'
            '      } catch (e) { /* ignore transient errors */ }\n'
            '    }\n'
            '\n'
            '    function drawTags(data) {\n'
            '      const img = document.getElementById("cam-img");\n'
            '      const canvas = document.getElementById("cam-canvas");\n'
            '      const ctx = canvas.getContext("2d");\n'
            '      const cw = img.clientWidth, ch = img.clientHeight;\n'
            '      canvas.width = cw;\n'
            '      canvas.height = ch;\n'
            '      ctx.clearRect(0, 0, cw, ch);\n'
            '      if (!data.width || !data.height) return;\n'
            '      const scale = Math.min(cw / data.width, ch / data.height);\n'
            '      const offX = (cw - data.width * scale) / 2;\n'
            '      const offY = (ch - data.height * scale) / 2;\n'
            '      ctx.lineWidth = 2;\n'
            '      ctx.font = "12px sans-serif";\n'
            '      ctx.textBaseline = "top";\n'
            '      (data.boxes || []).forEach((b) => {\n'
            '        const x = offX + b.x1 * scale;\n'
            '        const y = offY + b.y1 * scale;\n'
            '        const w = (b.x2 - b.x1) * scale;\n'
            '        const h = (b.y2 - b.y1) * scale;\n'
            '        ctx.strokeStyle = "#34d399";\n'
            '        ctx.strokeRect(x, y, w, h);\n'
            '        const label = `${b.label} ${Math.round(b.conf * 100)}%`;\n'
            '        const textW = ctx.measureText(label).width;\n'
            '        ctx.fillStyle = "rgba(5, 46, 29, 0.85)";\n'
            '        ctx.fillRect(x, Math.max(0, y - 16), textW + 8, 16);\n'
            '        ctx.fillStyle = "#34d399";\n'
            '        ctx.fillText(label, x + 4, Math.max(0, y - 16) + 2);\n'
            '      });\n'
            '    }\n'
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
    vision.disable(device_id)


# --- video proxy ---
# The hub is the sole consumer of the ESP32's raw MJPEG stream (its firmware
# doesn't reliably tolerate more than one concurrent client); browsers and the
# object detector both get frames relayed through here instead.

@app.get("/api/devices/{device_id}/stream")
async def proxy_stream(device_id: str):
    row = db.get_device(device_id)
    if row is None:
        raise HTTPException(404, "device not found")
    meta = json.loads(dict(row).get("meta") or "{}")
    ip = meta.get("ip")
    if not ip:
        raise HTTPException(400, "device IP unknown; cannot start stream")

    broadcaster = streaming.get_broadcaster(device_id, f"http://{ip}:81/stream")
    sub_id, frame_queue = broadcaster.subscribe()

    def gen():
        try:
            while True:
                try:
                    jpg = frame_queue.get(timeout=20)
                except queue.Empty:
                    continue
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(jpg)).encode() + b"\r\n\r\n" +
                    jpg + b"\r\n"
                )
        finally:
            broadcaster.unsubscribe(sub_id)

    return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")


# --- object tagging ---

class TaggingRequest(BaseModel):
    enabled: bool


@app.post("/api/devices/{device_id}/tagging")
async def set_tagging(device_id: str, req: TaggingRequest):
    row = db.get_device(device_id)
    if row is None:
        raise HTTPException(404, "device not found")
    if req.enabled:
        meta = json.loads(dict(row).get("meta") or "{}")
        ip = meta.get("ip")
        if not ip:
            raise HTTPException(400, "device IP unknown; cannot start tagging")
        vision.enable(device_id, f"http://{ip}:81/stream")
    else:
        vision.disable(device_id)
    return {"enabled": req.enabled}


@app.get("/api/devices/{device_id}/tags")
async def get_tags(device_id: str):
    tags = vision.get_tags(device_id)
    if tags is None:
        return {"enabled": False, "ts": 0, "width": 0, "height": 0, "boxes": []}
    return {**tags, "enabled": True}


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
