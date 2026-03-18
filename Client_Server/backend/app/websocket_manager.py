from collections import defaultdict

from fastapi import WebSocket


class WebSocketManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, task_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._connections[task_id].add(ws)

    def disconnect(self, task_id: str, ws: WebSocket) -> None:
        self._connections[task_id].discard(ws)
        if not self._connections[task_id]:
            self._connections.pop(task_id, None)

    async def broadcast(self, task_id: str, payload: dict) -> None:
        peers = list(self._connections.get(task_id, set()))
        for ws in peers:
            try:
                await ws.send_json(payload)
            except Exception:
                self.disconnect(task_id, ws)


ws_manager = WebSocketManager()
