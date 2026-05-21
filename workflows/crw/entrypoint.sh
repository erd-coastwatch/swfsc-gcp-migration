#!/bin/bash
set -euo pipefail

cd /app

echo "Preparing writable environment in /tmp..."
export HOME=/tmp

mkdir -p /tmp/work \
         /tmp/monthly \
         /tmp/daily

# ---------------------------------------------------------
# GCS config
# ---------------------------------------------------------
GCS_BUCKET="${GCS_BUCKET:-YOUR_PRODUCTION_BUCKET}"
JOB_TYPE="${JOB_TYPE:-monthly}"          # "monthly" or "daily"
LOOKBACK_DAYS="${LOOKBACK_DAYS:-3}"      # only used by daily

echo "-----------------------------------------------------"
echo "Starting CRW SST/SSTA update"
echo "Job type:      ${JOB_TYPE}"
echo "Bucket:        ${GCS_BUCKET}"
if [[ "${JOB_TYPE}" == "daily" ]]; then
  echo "Lookback days: ${LOOKBACK_DAYS}"
fi
echo "-----------------------------------------------------"

if [[ "${JOB_TYPE}" == "daily" ]]; then
  python scripts/control_crw_daily.py
elif [[ "${JOB_TYPE}" == "monthly" ]]; then
  python scripts/control_crw_monthly.py
else
  echo "ERROR: unknown JOB_TYPE '${JOB_TYPE}'. Must be 'monthly' or 'daily'." >&2
  exit 1
fi

echo "-----------------------------------------------------"
echo "CRW ${JOB_TYPE} SST/SSTA update completed successfully."
echo "-----------------------------------------------------"