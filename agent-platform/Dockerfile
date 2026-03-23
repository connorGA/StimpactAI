FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY agent-platform /app/agent-platform
COPY shared /app/shared

RUN python -m pip install --upgrade pip && \
    python -m pip install --no-cache-dir /app/agent-platform

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "api.main:app", "--app-dir", "agent-platform", "--host", "0.0.0.0", "--port", "8000"]
