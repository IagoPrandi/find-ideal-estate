FROM mcr.microsoft.com/playwright/python:v1.50.0-jammy

WORKDIR /app

RUN apt-get update \
	&& apt-get install -y --no-install-recommends xvfb \
	&& rm -rf /var/lib/apt/lists/*

# Dependencias Python
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Codigo
COPY apps/api ./apps/api
COPY packages/contracts ./packages/contracts
COPY infra ./infra
COPY alembic.ini ./alembic.ini
COPY docker/entrypoint.sh ./docker/entrypoint.sh

RUN chmod +x ./docker/entrypoint.sh

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/apps/api:/app/apps/api/src:/app/packages/contracts

ENTRYPOINT ["/app/docker/entrypoint.sh"]

EXPOSE 8000
