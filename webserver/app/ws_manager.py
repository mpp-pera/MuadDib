from fastapi import WebSocket
from .packet import Packet


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, WebSocket] = {}

    async def connect(self, device_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._connections[device_id] = ws

    def disconnect(self, device_id: str) -> None:
        self._connections.pop(device_id, None)

    def is_connected(self, device_id: str) -> bool:
        return device_id in self._connections

    async def send(self, device_id: str, pkt: Packet) -> bool:
        ws = self._connections.get(device_id)
        if ws is None:
            return False
        await ws.send_text(pkt.model_dump_json())
        return True

    async def broadcast(self, pkt: Packet) -> None:
        data = pkt.model_dump_json()
        for ws in list(self._connections.values()):
            await ws.send_text(data)

    @property
    def connected_ids(self) -> list[str]:
        return list(self._connections.keys())


manager = ConnectionManager()
