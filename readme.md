This is the application to read asset rates from https://rates.emcont.com/ and monitor it via websockets.
Components:
1. FastAPI WebSocket server.
2. Quotes fetcher worker.
3. Shared (some DB logic and docker base image).
4. Redis - as message broker for asset rate instant updates via pubsub.
5. ClickHouse - main DB to store assets and rate history.

Each component has own Dockerfile and works as a separated service.
DB table structure is created from FastAPI component.
Before run make sure that you have `.env` file with required variables:
* CLICKHOUSE_USER
* CLICKHOUSE_PASSWORD
* CLICKHOUSE_FETCHER_USER
* CLICKHOUSE_FETCHER_PASSWORD

Make sure that all ClickHouse users have sufficient read-write rights to default database.

To run application run:
```
make up
```

Using WebSocket client connect to `ws://0.0.0.0:8080/`.
Then send messages with actions:
1. `{"action": "assets"}` - returns array of id and name of all DB assets.
2. `{"action": "subscribe", "assetId": 1}` - subscribes to asset with required id and client will receive asset rate history for the last 30 minutes
and then rate updates for the asset every 1 second until switch to another asset or disconnect. If another subscribe message received, websocket context will be switched to new asset id.

Main further improvement - make unit and integration tests.