from collections.abc import Callable
from .packet import Packet, error_packet

_handlers: dict[str, Callable] = {}


def handler(msg_type: str):
    """Decorator: registers a coroutine as the handler for msg_type."""
    def decorator(fn: Callable) -> Callable:
        _handlers[msg_type] = fn
        return fn
    return decorator


async def dispatch(pkt: Packet) -> Packet:
    fn = _handlers.get(pkt.type)
    if fn is None:
        return error_packet(pkt, f"unknown message type: {pkt.type!r}")
    return await fn(pkt)
