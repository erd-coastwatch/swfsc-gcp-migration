# Dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        netcdf-bin \
    && rm -rf /var/lib/apt/lists/* \
    && which nccopy

WORKDIR /app

COPY config/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY scripts/ scripts/
COPY config/config.yaml config/config.yaml
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh \
    && sed -i 's/\r//' entrypoint.sh

ENV PYTHONPATH="/app/scripts"

ENTRYPOINT ["./entrypoint.sh"]