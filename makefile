build-base:
	docker build -f shared/Dockerfile -t base-image shared

build-server: build-base
	docker build -f ws_server/Dockerfile -t ws_server ws_server

build-fetcher: build-base
	docker build -f fetcher/Dockerfile -t quotes-fetcher fetcher

build: build-base build-server build-fetcher

up: build
	docker compose up --build
