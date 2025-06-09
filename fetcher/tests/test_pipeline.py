from datetime import datetime

import pytest
from unittest.mock import AsyncMock, MagicMock
import json

from fetcher.src.main import save_to_db, publish_to_redis, AssetRate


@pytest.mark.asyncio
async def test_full_pipeline():
    timestamp = datetime.now().timestamp()
    quotes = [
        AssetRate(asset_id=1, value=1.235, timestamp=timestamp),
        AssetRate(asset_id=2, value=1.112, timestamp=timestamp),
    ]

    # --- Mock ClickHouse client
    mock_clickhouse = MagicMock()
    mock_clickhouse.insert = AsyncMock()

    # --- Mock Redis client
    mock_redis = MagicMock()
    mock_redis.publish = AsyncMock()

    # --- Run tested functions
    await save_to_db(quotes, mock_clickhouse)
    await publish_to_redis(quotes, mock_redis)

    # --- Assertions
    mock_clickhouse.insert.assert_called_once_with(
        "quotes",
        [
            [quote.asset_id, datetime.fromtimestamp(quote.timestamp), quote.value]
            for quote in quotes
        ],
        column_names=['asset_id', 'date', 'value']
    )

    assert mock_redis.publish.call_count == len(quotes)
    mock_redis.publish.assert_any_call("quote: 1", json.dumps(quotes[0].__dict__))
    mock_redis.publish.assert_any_call("quote: 2", json.dumps(quotes[1].__dict__))
