FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src
COPY scripts ./scripts
COPY docs/movia_knowledge_source ./docs/movia_knowledge_source
COPY frontend ./frontend
COPY platform_registry ./platform_registry

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir .

EXPOSE 8000

CMD ["uvicorn", "movia_sales_agent.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
