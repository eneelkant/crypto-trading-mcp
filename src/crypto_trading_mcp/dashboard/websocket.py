from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from crypto_trading_mcp.dashboard.event_bus import get_event_bus

ws_router = APIRouter()


class WebSocketManager:
    def __init__(self) -> None:
        self.connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.connections:
            self.connections.remove(websocket)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        for ws in list(self.connections):
            try:
                await ws.send_json(payload)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = WebSocketManager()


@ws_router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Live event stream. Disconnect must not affect trading."""
    bus = get_event_bus()
    queue = bus.subscribe_queue()
    await manager.connect(websocket)
    try:
        await websocket.send_json({"type": "connected", "TRADING_MODE": "PAPER"})
        # Replay recent history
        for event in bus.history(limit=50):
            await websocket.send_json({"type": "event", "event": event})
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=15.0)
                await websocket.send_json({"type": "event", "event": event.to_dict()})
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "heartbeat", "TRADING_MODE": "PAPER"})
            # Non-blocking receive for client pings / close
            try:
                msg = await asyncio.wait_for(websocket.receive_text(), timeout=0.01)
                if msg == "ping":
                    await websocket.send_json({"type": "pong"})
            except asyncio.TimeoutError:
                pass
            except WebSocketDisconnect:
                break
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        # Never raise into trading process
        pass
    finally:
        bus.unsubscribe_queue(queue)
        manager.disconnect(websocket)
