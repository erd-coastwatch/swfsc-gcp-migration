# Dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        netcdf-bin \
        wget \
        libhdf5-dev \
        libnetcdf-dev \
    && rm -rf /var/lib/apt/lists/* \
    && which nccopy

WORKDIR /app

COPY config/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY scripts/ scripts/
COPY templates/ templates/
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]