FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 ALPICTURIA_DATA=/data
RUN apt-get update && apt-get install -y --no-install-recommends build-essential cmake libopenblas-dev && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY web/requirements.txt web/requirements-ai.txt /app/
RUN pip install -r requirements.txt -r requirements-ai.txt
RUN useradd --create-home --uid 10001 alpicturia && mkdir /data && chown alpicturia:alpicturia /data
COPY --chown=alpicturia:alpicturia web/alpicturia /app/alpicturia
USER alpicturia
EXPOSE 8000
CMD ["uvicorn","alpicturia.app:app","--host","0.0.0.0","--port","8000","--no-access-log"]
