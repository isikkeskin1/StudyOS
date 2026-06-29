FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY backend/pyproject.toml ./pyproject.toml
COPY backend/alembic.ini ./alembic.ini
COPY backend/alembic ./alembic
COPY backend/app ./app
COPY backend/scripts ./scripts

RUN pip install --upgrade pip && pip install .

RUN useradd --create-home --uid 10001 studyos \
    && mkdir -p /data/uploads \
    && chown -R studyos:studyos /app /data

USER studyos

ENV STUDYOS_ENV=production \
    STUDYOS_DATA_DIR=/data/uploads

EXPOSE 8000

ENTRYPOINT ["./scripts/production-start.sh"]
