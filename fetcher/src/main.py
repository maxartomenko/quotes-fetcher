import json
import logging
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Final

import asyncio
import aiohttp
import redis
import clickhouse_connect

import shared.src.db_handler as shared_db_handler
from fetcher.src.config import settings

RATES_URL: Final[str] = "https://rates.emcont.com/"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class AssetRate:
    asset_id: int
    timestamp: float
    value: float
    #  TODO: better to rework with pydantic and validation


async def worker() -> None:
    redis_client = await redis.asyncio.from_url(
        f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}",
        db=settings.REDIS_DB,
        password=settings.REDIS_PASSWORD or None,
        decode_responses=True,
    )

    clickhouse_client = await shared_db_handler.get_async_connection(
        host=settings.CLICKHOUSE_HOST,
        port=settings.CLICKHOUSE_PORT,
        username=settings.CLICKHOUSE_USER,
        password=settings.CLICKHOUSE_PASSWORD,
        database=settings.CLICKHOUSE_DB,
    )

    logger.info("Quotes fetcher has been started.")

    assets = {}
    while not assets:
        assets = await shared_db_handler.get_assets(clickhouse_client=clickhouse_client)
        await asyncio.sleep(5)
    logger.info("Assets has been uploaded.")
    assets = {v: k for k, v in assets.items()}

    while True:
        quotes = await fetch_quotes(assets=assets)
        logger.debug("Fetched %s quotes", str(quotes))
        if quotes:
            async with asyncio.TaskGroup() as tg:
                tg.create_task(save_to_db(quotes, clickhouse_client))
                tg.create_task(publish_to_redis(quotes, redis_client))
        #    TODO: group exceptions
        await asyncio.sleep(1)


async def fetch_quotes(assets: dict[str, int]) -> list[AssetRate]:
    response_body: dict[str, Any] = {}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(RATES_URL) as response:
                response.raise_for_status()
                response_text = await response.text()
                if response_text := re.sub(r"^null\(|\);\s*$", "", response_text):
                    response_body = json.loads(response_text)
    except aiohttp.ClientError as e:
        logger.error(f"HTTP error occurred: {e}")
        return []

    if not response_body:
        return []

    timestamp = datetime.now(timezone.utc).timestamp()
    return [
        AssetRate(
            asset_id=assets[rate["Symbol"]],
            timestamp=timestamp,
            value=(rate.get("Bid", 0) + rate.get("Ask", 0)) / 2,
        )
        for rate in response_body.get("Rates", [])
        if rate["Symbol"] in assets
    ]


async def publish_to_redis(
    quotes: list[AssetRate], redis_client: redis.asyncio.Redis
) -> None:
    for quote in quotes:
        await redis_client.publish(
            f"quote: {quote.asset_id}", json.dumps(asdict(quote))
        )


async def save_to_db(
    quotes: list[AssetRate], clickhouse_client: clickhouse_connect.driver.AsyncClient
) -> None:
    await clickhouse_client.insert(
        "quotes",
        [
            [quote.asset_id, datetime.fromtimestamp(quote.timestamp), quote.value]
            for quote in quotes
        ],
        column_names=["asset_id", "date", "value"],
    )


if __name__ == "__main__":
    asyncio.run(worker())
