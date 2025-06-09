import asyncio
import logging

import clickhouse_connect
from clickhouse_connect.driver.exceptions import ClickHouseError, OperationalError


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def get_async_connection(
    *, host: str, port: int, username: str, password: str, database: str
) -> clickhouse_connect.driver.AsyncClient:
    for attempt in range(1, 3):
        try:
            clickhouse_client = await clickhouse_connect.get_async_client(
                host=host,
                port=port,
                username=username,
                password=password,
                database=database,
            )
            logger.info(f"Connected to ClickHouse on attempt {attempt}")
            return clickhouse_client
        except OperationalError:
            logger.info("ClickHouse not ready yet...")
        await asyncio.sleep(3)
    else:
        raise RuntimeError("Failed to connect to ClickHouse.")


async def get_assets(
    *, clickhouse_client: clickhouse_connect.driver.AsyncClient
) -> dict[int, str]:
    try:
        query_result = await clickhouse_client.query("SELECT id, name FROM assets")
        return {int(row[0]): row[1] for row in query_result.result_rows}
    except ClickHouseError as e:
        logger.error(f"ClickHouse error fetching assets: {e}")
        return {}
