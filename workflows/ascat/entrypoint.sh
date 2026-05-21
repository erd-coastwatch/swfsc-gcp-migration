#!/bin/bash
set -euo pipefail

cd /app

echo "Preparing writable environment in /tmp..."
export HOME=/tmp

mkdir -p /tmp/data/work \
         /tmp/data/work_bk \
         /tmp/data/results/4hr \
         /tmp/data/results/1day \
         /tmp/data/results/3day \
         /tmp/data/results/7day \
         /tmp/data/results/mday \
         /tmp/data/staging/4hr \
         /tmp/logs

# ---------------------------------------------------------
# GCS bucket / prefix config — must match config YAMLs
# ---------------------------------------------------------
PROD_BUCKET="${PROD_BUCKET:-YOUR_PRODUCTION_BUCKET}"
ARCHIVE_4HR="${ARCHIVE_4HR:-edge/ASCAT/4hr}"
ARCHIVE_1DAY="${ARCHIVE_1DAY:-edge/ASCAT/1day}"

# ---------------------------------------------------------
# Cache warming — pull required files from GCS before processing
# ---------------------------------------------------------
warm_cache_daily() {
    # Pull the last 8 days of 4hr files in a single parallel gsutil call
    # so 1/3/7-day composites have enough input data.
    echo "Warming cache: pulling last 8 days of 4hr files from GCS..."

    TODAY=$(date -u +%Y%m%d)
    SOURCES=()

    for i in $(seq 1 8); do
        # date arithmetic compatible with both Linux (Cloud Run) and macOS (local)
        DAY=$(date -u -d "${TODAY} - ${i} days" +%Y%m%d 2>/dev/null \
              || date -u -v-${i}d -j -f "%Y%m%d" "${TODAY}" +%Y%m%d)
        DAY_YEAR="${DAY:0:4}"
        mkdir -p "/tmp/data/results/4hr/${DAY_YEAR}"
        SOURCES+=("gs://${PROD_BUCKET}/${ARCHIVE_4HR}/${DAY_YEAR}/ascatc_${DAY}*.nc")
    done

    # All date globs passed to one gsutil -m cp — transfers run in parallel
    gsutil -m cp -n "${SOURCES[@]}" "/tmp/data/results/4hr/${DAY_YEAR}/" 2>/dev/null || true

    echo "Cache warm complete."
}

warm_cache_monthly() {
    # Pull all 1day files for the previous month in a single parallel gsutil call.
    echo "Warming cache: pulling previous month 1day files from GCS..."

    FIRST_THIS_MONTH=$(date -u +%Y%m01)
    PREV_MONTH=$(date -u -d "${FIRST_THIS_MONTH} - 1 day" +%Y%m 2>/dev/null \
                 || date -u -v-1d -j -f "%Y%m%d" "${FIRST_THIS_MONTH}" +%Y%m)
    PREV_YEAR="${PREV_MONTH:0:4}"

    LOCAL_DIR="/tmp/data/results/1day/${PREV_YEAR}"
    mkdir -p "${LOCAL_DIR}"

    echo "Pulling gs://${PROD_BUCKET}/${ARCHIVE_1DAY}/${PREV_YEAR}/ascatc_${PREV_MONTH}*.nc -> ${LOCAL_DIR}/"
    gsutil -m cp -n \
        "gs://${PROD_BUCKET}/${ARCHIVE_1DAY}/${PREV_YEAR}/ascatc_${PREV_MONTH}*.nc" \
        "${LOCAL_DIR}/"

    echo "Cache warm complete. Files pulled:"
    ls -lh "${LOCAL_DIR}/" | grep "${PREV_MONTH}" || echo "WARNING: no files found for ${PREV_MONTH}"
}

# ---------------------------------------------------------
# Determine job mode
# ---------------------------------------------------------
MODE="${JOB_MODE:-daily}"
echo "-----------------------------------------------------"
echo "Starting ASCAT-C workflow: ${MODE}"
echo "-----------------------------------------------------"

case "$MODE" in
  # -------------------------------------------------------
  # DAILY: Warm cache, ingest new 4hr files, build composites
  # -------------------------------------------------------
  daily)
    warm_cache_daily

    echo "[1/2] Running 4-hour ASCAT-C ingestion..."
    python -m scripts.download_ascat_4hr \
      --config config/config_update.yaml \
      --log-level "${LOG_LEVEL:-INFO}" \
      ${DRY_RUN:+--dry-run}

    echo "[2/2] Running multi-day composites..."
    python -m scripts.ascat_composite_control multi-day \
      --config config/config_composite.yaml \
      --log-level "${LOG_LEVEL:-INFO}" \
      ${OVERWRITE:+--overwrite} \
      ${BACKFILL:+--backfill} \
      ${DRY_RUN:+--dry-run}
    ;;

  # -------------------------------------------------------
  # MONTHLY: Warm cache, build monthly composite
  # -------------------------------------------------------
  monthly)
    warm_cache_monthly

    echo "[1/1] Running monthly ASCAT-C composite..."
    python -m scripts.ascat_composite_control monthly \
      --config config/config_composite.yaml \
      --log-level "${LOG_LEVEL:-INFO}" \
      ${OVERWRITE:+--overwrite} \
      ${DRY_RUN:+--dry-run}
    ;;

  *)
    echo "ERROR: Unknown JOB_MODE='${MODE}'. Valid values: daily, monthly"
    exit 2
    ;;
esac

echo "-----------------------------------------------------"
echo "ASCAT-C workflow '${MODE}' completed successfully."
echo "-----------------------------------------------------"