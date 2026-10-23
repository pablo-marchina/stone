FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TAPI_ENV=local TAPI_EXTERNAL_OPERATIONS_ENABLED=false TAPI_PROJECT_ROOT=/app
WORKDIR /app
COPY pyproject.toml .
COPY src ./src
COPY config ./config
RUN pip install --no-cache-dir . && useradd --create-home --uid 10001 tapi
USER tapi
EXPOSE 8000
CMD ["uvicorn", "tapi_gate0.api:app", "--host", "0.0.0.0", "--port", "8000"]
