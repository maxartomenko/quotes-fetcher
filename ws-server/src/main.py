import logging
from contextlib import asynccontextmanager
from typing import Any

import redis
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from config import settings
from db_handler import init_db_structure, get_asset_by_id
import shared.src.db_handler as shared_db_handler
from shared.src.db_handler import get_assets
from ws_handler import WebSocketManager, ResponseActions, RequestActions

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = await redis.asyncio.from_url(
        f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}",
        db=settings.REDIS_DB,
        password=settings.REDIS_PASSWORD or None,
        decode_responses=True
    )

    clickhouse_client = await shared_db_handler.get_async_connection(
        host=settings.CLICKHOUSE_HOST,
        port=settings.CLICKHOUSE_PORT,
        username=settings.CLICKHOUSE_USER,
        password=settings.CLICKHOUSE_PASSWORD,
        database=settings.CLICKHOUSE_DB,
    )

    app.state.clickhouse = clickhouse_client
    await init_db_structure(clickhouse_client=clickhouse_client)

    yield

    await app.state.redis.close()
    await app.state.clickhouse.close()


app = FastAPI(lifespan=lifespan)
ws_manager = WebSocketManager(app=app)


async def handle_assets(ws: WebSocket):
    assets = await get_assets(clickhouse_client=ws.app.state.clickhouse)
    await ws.send_json({
        "action": ResponseActions.ASSETS,
            "message": {
                "assets": [
                    {
                        "id": _id,
                        "name": asset
                    } for _id, asset in assets.items()
                ]
            }
        })


async def handle_subscribe(ws: WebSocket, request: dict[str, Any]):
    asset_id = request.get("assetId", 0)
    asset = await get_asset_by_id(
        clickhouse_client=ws.app.state.clickhouse,
        asset_id=asset_id
    )
    if asset is None:
        await ws.send_json({
            "action": ResponseActions.ERROR,
            "code": 412,
            "message": "Asset not found"
        })
        return

    await ws_manager.subscribe(ws=ws, asset=asset)


async def handle_unknown(ws_id: int, action: str):
    await ws_manager.send_error(ws_id, f"Unknown action: {action}")


@app.websocket("/")
async def websocket_handler(ws: WebSocket):
    await ws.accept()
    ws_id = ws_manager.connect(ws)

    try:
        async for request in ws.iter_json():
            action = request.get("action")

            match action:
                case RequestActions.ASSETS:
                    await handle_assets(ws)

                case RequestActions.SUBSCRIBE:
                    await handle_subscribe(ws=ws, request=request)

                case _:
                    await handle_unknown(ws_id, action)

    except WebSocketDisconnect:
        logger.info(f"[disconnect] {ws_id}")
    finally:
        await ws_manager.disconnect(ws_id)
