FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    gfortran \
    netcdf-bin \
    libnetcdf-dev \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY config/requirements.txt /app/config/requirements.txt
RUN pip install --no-cache-dir -r /app/config/requirements.txt

COPY . /app
RUN chmod +x /app/entrypoint.sh /app/scripts/*.py

ENV PYTHONUNBUFFERED=1
ENV HOME=/tmp

ENTRYPOINT ["/app/entrypoint.sh"]
