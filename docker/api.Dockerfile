FROM mcr.microsoft.com/playwright/python:v1.50.0-jammy

WORKDIR /app

# Dependencias Python
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Codigo
COPY app ./app
COPY core ./core
COPY adapters ./adapters
COPY cods_ok ./cods_ok
COPY platforms.yaml ./platforms.yaml
COPY *.py ./

ENV PYTHONUNBUFFERED=1

EXPOSE 8000
