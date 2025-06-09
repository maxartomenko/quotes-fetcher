import asyncio
import enum
import logging
from dataclasses import asdict
from typing import Any

import fastapi
import redis
from fastapi import WebSocket
import json

from db_handler import get_quotes_for_period, Asset


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class RequestActions(enum.StrEnum):
    ASSETS = "assets"
    SUBSCRIBE = "subscribe"


class ResponseActions(enum.StrEnum):
    ASSETS = "assets"
    ASSET_HISTORY = "asset_history"
    POINT = "point"
    ERROR = "error"


class WebSocketManager:
    def __init__(
        self,
        *,
        app: fastapi.FastAPI
    ):
        self.app = app
        self._connections: dict[int, dict[str, Any]] = {}

    def connect(self, websocket: WebSocket):
        ws_id = id(websocket)
        self._connections[ws_id] = {"websocket": websocket, "asset": None, "task": None}
        return ws_id

    async def disconnect(self, ws_id: int):
        entry = self._connections.get(ws_id)
        if entry:
            task = entry.get("task")
            if task:
                task.cancel()
                try:
                    await task
                except:
                    pass
            self._connections.pop(ws_id, None)

    async def subscribe(self, *, ws: WebSocket, asset: Asset):
        entry = self._connections.get(id(ws))
        print(id(ws))
        print(entry)
        if not entry:
            return

        if entry["task"]:
            entry["task"].cancel()
            try:
                await entry["task"]
            except asyncio.exceptions.CancelledError:
                pass

        websocket = entry["websocket"]

        quotes = await get_quotes_for_period(
            clickhouse_client=ws.app.state.clickhouse,
            asset_id=asset._id
        )
        await websocket.send_json({
            "action": ResponseActions.ASSET_HISTORY,
            "message": {
                "points": [
                    {
                        "assetName": asset.name,
                        **asdict(quote)
                    }
                    for quote in quotes
                ]
            }
        })

        async def push_quotes_loop():
            redis_client: redis.asyncio.Redis = self.app.state.redis
            pubsub = redis_client.pubsub()
            channel = f"quote: {asset._id}"
            logger.info("channel %s", channel)
            await pubsub.subscribe(channel)
            try:
                async for msg in pubsub.listen():
                    logger.info(msg)
                    if msg["type"] != "message":
                        continue
                    quote = json.loads(msg["data"])
                    await websocket.send_json({
                        "action": ResponseActions.POINT,
                        "message": {
                            "assetName": asset.name,
                            **quote
                        }
                    })
            except Exception as e:
                logger.error(f"[push_quotes_loop] error: {e}")
            finally:
                await pubsub.unsubscribe(channel)

        # update entry
        task = asyncio.create_task(push_quotes_loop())
        entry["asset"] = asset._id
        entry["task"] = task

    async def send_error(self, ws_id: int, message: str):
        entry = self._connections.get(ws_id)
        if entry:
            await entry["websocket"].send_json({
                "action": ResponseActions.ERROR,
                "message": message
            })
