FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml setup.py README.md alembic.ini ./
COPY app ./app
COPY migrations ./migrations
COPY rag ./rag
COPY evals ./evals
COPY scripts ./scripts

RUN pip install --upgrade pip && pip install .

CMD ["python", "-m", "app.api.main"]
