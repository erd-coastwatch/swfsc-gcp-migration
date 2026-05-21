#!/bin/bash
set -euo pipefail

cd /app
export HOME=/tmp

mkdir -p /tmp/work/mh1_primprod_daily \
         /tmp/work/mh1_primprod_3day \
         /tmp/work/mh1_primprod_8day \
         /tmp/results/mh1_primprod_daily \
         /tmp/results/mh1_primprod_3day \
         /tmp/results/mh1_primprod_8day

GCS_BUCKET="${GCS_BUCKET:-YOUR_PRODUCTION_BUCKET}"
MODE="${MODE:-daily}"
REFERENCE_DIR="${REFERENCE_DIR:-/app/templates}"
WORLD_DAYLENGTH="${WORLD_DAYLENGTH:-worlddaylen.nc}"

if [[ ! -f "${REFERENCE_DIR}/${WORLD_DAYLENGTH}" ]]; then
  echo "ERROR: ${REFERENCE_DIR}/${WORLD_DAYLENGTH} is missing. Put your reference .nc files in templates/ before building." >&2
  exit 2
fi

echo "-----------------------------------------------------"
echo "Starting MH1 Primary Productivity update | mode: ${MODE}"
echo "Bucket: ${GCS_BUCKET}"
echo "Reference dir: ${REFERENCE_DIR}"
echo "Daylength file: ${WORLD_DAYLENGTH}"
echo "-----------------------------------------------------"

export PYTHONPATH="/app:${PYTHONPATH:-}"

python scripts/control_mh1_primprod.py