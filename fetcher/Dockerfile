FROM base-image

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ./src ./fetcher/src

ENV PYTHONPATH=/app

CMD ["python", "fetcher/src/main.py"]