build-base:
	docker build -f shared/Dockerfile -t base-image shared

build-server: build-base
	docker build -f ws-server/Dockerfile -t ws-server ws-server

build-fetcher: build-base
	docker build -f fetcher/Dockerfile -t quotes-fetcher fetcher

build: build-base build-server build-fetcher

up: build
	docker compose up --build
