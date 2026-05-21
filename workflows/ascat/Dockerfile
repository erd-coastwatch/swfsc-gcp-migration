# ASCAT-C Wind Processing Pipeline
FROM python:3.11-slim

# System dependencies: NCO tools (ncks, ncra) + netcdf-bin (nccopy) + GCloud SDK
RUN apt-get update && apt-get install -y \
    wget curl gnupg dos2unix \
    nco \
    netcdf-bin \
    && rm -rf /var/lib/apt/lists/*

# Install Google Cloud SDK
RUN echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | \
    tee -a /etc/apt/sources.list.d/google-cloud-sdk.list && \
    curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | \
    gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg && \
    apt-get update && apt-get install -y google-cloud-cli && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python dependencies
COPY config/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Application source
COPY config/           ./config/
COPY src/              ./src/
COPY scripts/          ./scripts/
COPY templates/        ./templates/
COPY entrypoint.sh     ./entrypoint.sh

RUN dos2unix entrypoint.sh && chmod +x entrypoint.sh

ENV PYTHONPATH="/app:/app/src" \
    PYTHONUNBUFFERED=1 \
    HOME="/tmp"

ENTRYPOINT ["/bin/bash", "/app/entrypoint.sh"]