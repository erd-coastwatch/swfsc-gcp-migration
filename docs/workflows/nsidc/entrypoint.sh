#!/bin/bash
set -euo pipefail

cd /app

echo "Preparing writable environment in /tmp..."
export HOME=/tmp
export PYTHONPATH="/app/scripts"

mkdir -p /tmp/work

GCS_BUCKET="${GCS_BUCKET:-YOUR_PRODUCTION_BUCKET}"
MODE="${MODE:-daily}"

echo "-----------------------------------------------------"
echo "Starting NSIDC CDR processing | mode: ${MODE}"
echo "Bucket: ${GCS_BUCKET}"
echo "-----------------------------------------------------"

python -u scripts/control_nsidc.py

echo "-----------------------------------------------------"
echo "NSIDC CDR processing completed successfully."
echo "-----------------------------------------------------"