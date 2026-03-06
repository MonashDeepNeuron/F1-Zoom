"""F1 Live Timing client — connects to the official SignalR feed.

Set F1_MODE=live to activate. Requires a live session to be running on
livetiming.formula1.com. This module handles the legacy SignalR v1
negotiation / WebSocket handshake used by F1.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import urllib.parse
import zlib
from typing import Any

import aiohttp

logger = logging.getLogger("f1_client")

URL = "livetiming.formula1.com/signalr"
HUB = "Streaming"
TOPICS = [
    "Heartbeat",
    "ExtrapolatedClock",
    "TimingStats",
    "TimingAppData",
    "WeatherData",
    "TrackStatus",
    "SessionStatus",
    "DriverList",
    "RaceControlMessages",
    "SessionInfo",
    "SessionData",
    "LapCount",
    "TimingData",
    "ChampionshipPrediction",
    "Position.z",
    "CarData.z",
    "Position",
]


def _decompress_z(payload: Any) -> Any:
    """Decompress a base64+zlib-encoded payload (F1 .z topics)."""
    if not isinstance(payload, str):
        return payload
    try:
        raw = base64.b64decode(payload)
    except Exception:
        return payload
    for wbits in (-zlib.MAX_WBITS, zlib.MAX_WBITS, zlib.MAX_WBITS | 16):
        try:
            text = zlib.decompress(raw, wbits).decode("utf-8-sig")
            return json.loads(text)
        except Exception:
            continue
    return payload


def _extract_position_entries(data: Any) -> dict:
    """Pull the flat {driverNum: {X,Y,Z,Status}} dict out of F1 Position data.

    F1 sends positions as an array of timestamped snapshots:
      [ { "Timestamp": "...", "Entries": { "1": {...}, ... } } ]
    or as a dict with numeric keys for partial array updates:
      { "0": { "Timestamp": "...", "Entries": { "1": {...} } } }
    We merge all Entries dicts and return them flat.
    """
    entries: dict = {}
    items: list = []

    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        if "Entries" in data:
            return data["Entries"]
        items = list(data.values())

    for item in items:
        if isinstance(item, dict) and "Entries" in item:
            entries.update(item["Entries"])

    return entries


class F1LiveClient:
    def __init__(self, state_service: Any) -> None:
        self.ss = state_service

    async def _negotiate(self, session: aiohttp.ClientSession) -> tuple[str, str]:
        hub_data = json.dumps([{"name": HUB}])
        params = {"clientProtocol": "1.5", "connectionData": hub_data}
        url = f"https://{URL}/negotiate?{urllib.parse.urlencode(params)}"

        async with session.get(url) as resp:
            body = await resp.json()
            cookie = resp.headers.get("Set-Cookie", "")
        return body["ConnectionToken"], cookie

    async def run(self) -> None:
        """Connect, subscribe, then stream updates indefinitely."""
        async with aiohttp.ClientSession() as session:
            token, cookie = await self._negotiate(session)
            logger.info("Negotiated connection token")

            hub_data = json.dumps([{"name": HUB}])
            params = {
                "clientProtocol": "1.5",
                "transport": "webSockets",
                "connectionToken": token,
                "connectionData": hub_data,
            }
            ws_url = f"wss://{URL}/connect?{urllib.parse.urlencode(params)}"
            headers = {"Cookie": cookie} if cookie else {}

            async with session.ws_connect(ws_url, headers=headers) as ws:
                logger.info("WebSocket connected — subscribing to %d topics", len(TOPICS))
                subscribe_msg = json.dumps({
                    "H": HUB,
                    "M": "Subscribe",
                    "A": [TOPICS],
                    "I": 0,
                })
                await ws.send_str(subscribe_msg)

                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        self._handle_message(msg.data)
                    elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        logger.warning("WebSocket closed/error: %s", msg)
                        break

        logger.info("F1 live client disconnected")

    def _handle_message(self, raw: str) -> None:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return

        if "R" in data and isinstance(data["R"], dict):
            logger.info("Received initial state snapshot")
            state = data["R"]

            # Decompress any .z topics in the initial snapshot
            for key in list(state.keys()):
                if key.endswith(".z"):
                    state[key] = _decompress_z(state[key])

            # Normalise Position.z → Position with flat Entries
            if "Position.z" in state:
                entries = _extract_position_entries(state.pop("Position.z"))
                state.setdefault("Position", {})["Entries"] = entries

            self.ss.set_initial(state)
            return

        if "M" not in data:
            return

        for item in data["M"]:
            if item.get("M") != "feed" or not item.get("A"):
                continue
            args = item["A"]
            if len(args) < 2:
                continue

            topic = args[0]
            payload = args[1]

            # Decompress .z topics
            if topic.endswith(".z"):
                payload = _decompress_z(payload)
                base_topic = topic[:-2]
            else:
                base_topic = topic

            # Convert Position snapshots into the shape the frontend expects
            if base_topic == "Position":
                entries = _extract_position_entries(payload)
                if not entries:
                    continue
                update = {"Position": {"Entries": entries}}
            else:
                update = {base_topic: payload}

            asyncio.get_event_loop().create_task(self.ss.broadcast(update))
