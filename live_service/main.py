import asyncio
import copy
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("live_service")


def deep_merge(base: Any, update: Any) -> Any:
    """Recursively merge *update* into *base*, matching F1's incremental update pattern.

    Handles dict-into-dict and dict-with-numeric-keys-into-list merges so that
    partial updates from F1 (e.g. updating Sectors.0.Value) are applied correctly.
    """
    if isinstance(base, dict) and isinstance(update, dict):
        merged = dict(base)
        for key, value in update.items():
            if key in merged:
                merged[key] = deep_merge(merged[key], value)
            else:
                merged[key] = value
        return merged
    if isinstance(base, list) and isinstance(update, dict):
        result = list(base)
        for idx_str, value in update.items():
            try:
                idx = int(idx_str)
            except ValueError:
                continue
            while len(result) <= idx:
                result.append(None)
            result[idx] = deep_merge(result[idx], value) if result[idx] is not None else value
        return result
    return update


class StateService:
    """In-memory state store with broadcast fan-out to SSE subscribers."""

    def __init__(self) -> None:
        self.state: dict = {}
        self._subscribers: list[asyncio.Queue[str]] = []

    def set_initial(self, data: dict) -> None:
        self.state = copy.deepcopy(data)

    def apply_update(self, update: dict) -> None:
        self.state = deep_merge(self.state, update)

    async def broadcast(self, update: dict) -> None:
        self.apply_update(update)
        serialized = json.dumps(update)
        dead: list[asyncio.Queue[str]] = []
        for queue in self._subscribers:
            try:
                queue.put_nowait(serialized)
            except asyncio.QueueFull:
                dead.append(queue)
        for q in dead:
            self._subscribers.remove(q)

    def subscribe(self) -> asyncio.Queue[str]:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=512)
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[str]) -> None:
        try:
            self._subscribers.remove(queue)
        except ValueError:
            pass


state_service = StateService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    mode = os.environ.get("F1_MODE", "mock")
    task = None

    if mode == "live":
        from f1_client import F1LiveClient

        client = F1LiveClient(state_service)
        task = asyncio.create_task(client.run())
        logger.info("Started F1 live client")
    else:
        from mock import MockSession

        track_dir = os.environ.get(
            "TRACK_DATA_DIR",
            os.path.join(
                os.path.dirname(__file__),
                "..",
                "frontend",
                "public",
                "circuit_3d",
                "TrackCoordinateJS",
            ),
        )
        track_name = os.environ.get("TRACK_NAME", "Melbourne")
        session = MockSession(state_service, track_dir, track_name)
        task = asyncio.create_task(session.run())
        logger.info("Started mock session on %s", track_name)

    yield

    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/realtime")
async def sse_realtime(request: Request):
    queue = state_service.subscribe()

    async def event_generator():
        try:
            yield {"event": "initial", "data": json.dumps(state_service.state)}
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield {"event": "update", "data": data}
                except asyncio.TimeoutError:
                    yield {"event": "heartbeat", "data": ""}
        finally:
            state_service.unsubscribe(queue)

    return EventSourceResponse(event_generator())


@app.get("/api/state")
async def get_state():
    return state_service.state
