#!/bin/bash
set -euo pipefail

# ----------------------------
# SETTINGS — edit these
# ----------------------------
PROJECT_ID="YOUR_PROJECT_ID"
REGION="us-east4"

REPO_NAME="crw-processor"
IMAGE_NAME="crw-processor"
TAG="v1"

SERVICE_ACCOUNT="YOUR_SERVICE_ACCOUNT@${PROJECT_ID}.iam.gserviceaccount.com"

# Keep for Apple Silicon cross-compile; override with PLATFORM="" on amd64 hosts
PLATFORM="${PLATFORM:-linux/amd64}"

# Full Artifact Registry image path
IMAGE_PATH="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${IMAGE_NAME}:${TAG}"

# ----------------------------
# Prereq check
# ----------------------------
need() { command -v "$1" >/dev/null 2>&1 || { echo "Missing required command: $1" >&2; exit 1; }; }
need gcloud
need docker

echo "Using image: ${IMAGE_PATH}"

# ----------------------------
# 1) Build image
# ----------------------------
echo "Building Docker image..."
if [[ -n "${PLATFORM}" ]]; then
  docker buildx build --platform "${PLATFORM}" -t "${IMAGE_NAME}:${TAG}" --load .
else
  docker build -t "${IMAGE_NAME}:${TAG}" .
fi

# ----------------------------
# 2) gcloud project + Artifact Registry repo
# ----------------------------
echo "Setting gcloud project: ${PROJECT_ID}"
gcloud config set project "${PROJECT_ID}" >/dev/null

echo "Checking Artifact Registry repo: ${REPO_NAME} (${REGION})..."
if ! gcloud artifacts repositories describe "${REPO_NAME}" --location="${REGION}" >/dev/null 2>&1; then
  echo "Repo not found — creating..."
  gcloud artifacts repositories create "${REPO_NAME}" \
    --repository-format=docker \
    --location="${REGION}" \
    --description="Docker repository for CRW SST/SSTA processing"
else
  echo "Repo exists."
fi

echo "Configuring Docker auth for ${REGION}-docker.pkg.dev ..."
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

# ----------------------------
# 3) Tag + push
# ----------------------------
echo "Tagging and pushing image..."
docker tag "${IMAGE_NAME}:${TAG}" "${IMAGE_PATH}"
docker push "${IMAGE_PATH}"
echo "OK: pushed ${IMAGE_PATH}"

PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"

# ----------------------------
# 4a) Deploy Cloud Run Job — MONTHLY
# ----------------------------
echo "Deploying Cloud Run Job: crw-monthly-processor..."

gcloud run jobs deploy "crw-monthly-processor" \
  --image "${IMAGE_PATH}" \
  --service-account "${SERVICE_ACCOUNT}" \
  --tasks 1 \
  --max-retries 0 \
  --task-timeout "2h" \
  --region "${REGION}" \
  --memory "8Gi" \
  --cpu "4" \
  --set-env-vars "GCS_BUCKET=YOUR_PRODUCTION_BUCKET,JOB_TYPE=monthly,LOG_LEVEL=INFO"

# ----------------------------
# 4b) Deploy Cloud Run Job — DAILY
# ----------------------------
echo "Deploying Cloud Run Job: crw-daily-processor..."

gcloud run jobs deploy "crw-daily-processor" \
  --image "${IMAGE_PATH}" \
  --service-account "${SERVICE_ACCOUNT}" \
  --tasks 1 \
  --max-retries 0 \
  --task-timeout "2h" \
  --region "${REGION}" \
  --memory "8Gi" \
  --cpu "4" \
  --set-env-vars "GCS_BUCKET=YOUR_PRODUCTION_BUCKET,JOB_TYPE=daily,LOOKBACK_DAYS=3,LOG_LEVEL=INFO"

# ----------------------------
# 5a) Cloud Scheduler — MONTHLY
# ----------------------------
echo "Configuring Cloud Scheduler: crw-monthly-processor..."
gcloud scheduler jobs delete "crw-monthly-processor" --location "${REGION}" --quiet 2>/dev/null || true

# Mirror of the on-prem cron: 0 4 2,4,10,12,15,18 * * (04:00 PST)
gcloud scheduler jobs create http "crw-monthly-processor" \
  --location "${REGION}" \
  --schedule "0 4 2,4,10,12,15,18 * *" \
  --time-zone "America/Los_Angeles" \
  --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_NUMBER}/jobs/crw-monthly-processor:run" \
  --http-method POST \
  --oauth-service-account-email "${SERVICE_ACCOUNT}" \
  --oauth-token-scope "https://www.googleapis.com/auth/cloud-platform"

# ----------------------------
# 5b) Cloud Scheduler — DAILY
# ----------------------------
echo "Configuring Cloud Scheduler: crw-daily-processor..."
gcloud scheduler jobs delete "crw-daily-processor" --location "${REGION}" --quiet 2>/dev/null || true

# Runs every day at 10:00 AM PST. Controller skips dates already in GCS,
# so re-runs are safe and any missed days within LOOKBACK_DAYS are caught.
gcloud scheduler jobs create http "crw-daily-processor" \
  --location "${REGION}" \
  --schedule "0 10 * * *" \
  --time-zone "America/Los_Angeles" \
  --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_NUMBER}/jobs/crw-daily-processor:run" \
  --http-method POST \
  --oauth-service-account-email "${SERVICE_ACCOUNT}" \
  --oauth-token-scope "https://www.googleapis.com/auth/cloud-platform"

# ----------------------------
# Done
# ----------------------------
echo ""
echo "All done."
echo "Image:     ${IMAGE_PATH}"
echo ""
echo "Jobs & schedules:"
echo "  crw-monthly-processor  →  04:00 America/Los_Angeles, days 2,4,10,12,15,18"
echo "  crw-daily-processor    →  10:00 America/Los_Angeles, every day"