FROM mcr.microsoft.com/playwright/python:v1.50.0-jammy

WORKDIR /app

# Dependencias Python
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Codigo
COPY apps/api ./apps/api
COPY packages/contracts ./packages/contracts
COPY infra ./infra
COPY alembic.ini ./alembic.ini

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/apps/api:/app/apps/api/src:/app/packages/contracts

EXPOSE 8000
