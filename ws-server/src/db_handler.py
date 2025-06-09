from dataclasses import dataclass

import clickhouse_connect
import logging

from clickhouse_connect.driver.exceptions import ClickHouseError

logger = logging.getLogger("uvicorn.error")


@dataclass
class Asset:
    _id: int
    name: str


@dataclass
class AssetQuoteResponse:
    time: float
    assetId: int
    value: float


async def init_db_structure(clickhouse_client: clickhouse_connect.driver.AsyncClient) -> None:
    # Assets table
    await clickhouse_client.command("""
        CREATE TABLE IF NOT EXISTS assets (
            id Int16,
            name String
        ) ENGINE = MergeTree
        ORDER BY id;
    """)

    # Insert default assets
    result = await clickhouse_client.query("SELECT count() FROM assets")
    if result.result_rows[0][0] == 0:
        await clickhouse_client.insert(
            "assets",
            [
                [1, "EURUSD"],
                [2, "USDJPY"],
                [3, "GBPUSD"],
                [4, "AUDUSD"],
                [5, "USDCAD"],
            ],
            column_names=["id", "name"]
        )

    # Quotes (rates) table
    await clickhouse_client.command("""            
        CREATE TABLE IF NOT EXISTS quotes (
            asset_id Int16,
            date DateTime,
            value Float64
        )
        ENGINE = MergeTree
        PARTITION BY toDate(date)
        ORDER BY (asset_id, date);
    """)


async def get_quotes_for_period(
    *,
    asset_id: int,
    clickhouse_client: clickhouse_connect.driver.AsyncClient,
    period_minutes: int = 30
) -> list[AssetQuoteResponse]:
    try:
        query_result = await clickhouse_client.query("""
            SELECT date, value FROM quotes 
            WHERE asset_id = %(assetId)s AND date >= now() - INTERVAL %(minutes)s MINUTE
        """,
            parameters={
                "assetId": asset_id,
                "minutes": period_minutes
            }
        )
        return [
            AssetQuoteResponse(
                time=row[0].timestamp(),
                assetId=asset_id,
                value=row[1]
            )
            for row in query_result.result_rows
        ]
    except ClickHouseError as e:
        logger.error(f"ClickHouse error fetching quotes for asset {asset_id}: {e}")
        return []


async def get_asset_by_id(
    *,
    clickhouse_client: clickhouse_connect.driver.AsyncClient,
    asset_id: int
) -> Asset | None:
    try:
        query_result = await clickhouse_client.query(
            "SELECT id, name FROM assets WHERE id = %(assetId)s",
            parameters={"assetId": asset_id}
        )
        if query_result.result_rows:
            row = query_result.result_rows[0]
            return Asset(
                _id=int(row[0]),
                name=row[1]
            )
    except ClickHouseError as e:
        logger.error(f"ClickHouse error fetching assets: {e}")
    return None
