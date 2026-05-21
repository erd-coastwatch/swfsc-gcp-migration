#!/bin/bash
set -euo pipefail

# ----------------------------
# SETTINGS — edit these
# ----------------------------
PROJECT_ID="YOUR_PROJECT_ID"
REGION="us-east4"

REPO_NAME="ascat-processor"
IMAGE_NAME="ascat-processor"
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
    --description="Docker repository for ASCAT-C wind processing"
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

# ----------------------------
# 4) Deploy Cloud Run Jobs
# ----------------------------
echo "Deploying Cloud Run Jobs..."

deploy_job() {
  local job_name="$1"
  local job_mode="$2"
  local memory="$3"
  local cpu="$4"
  local timeout="$5"

  echo "Deploying job: ${job_name} (JOB_MODE=${job_mode})"
  gcloud run jobs deploy "${job_name}" \
    --image "${IMAGE_PATH}" \
    --service-account "${SERVICE_ACCOUNT}" \
    --tasks 1 \
    --max-retries 0 \
    --task-timeout "${timeout}" \
    --region "${REGION}" \
    --memory "${memory}" \
    --cpu "${cpu}" \
    --set-env-vars "JOB_MODE=${job_mode},LOG_LEVEL=INFO"
}

# Daily job: 4-hr ingest + 1/3/7-day composites
deploy_job "ascat-daily-processor"   "daily"   "32Gi" "8" "2h"

# Monthly job: monthly composite from daily files
deploy_job "ascat-monthly-processor" "monthly" "32Gi" "8" "2h"

# ----------------------------
# 5) Cloud Scheduler
# ----------------------------
echo "Configuring Cloud Scheduler..."

PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"

create_scheduler() {
  local scheduler_name="$1"
  local job_name="$2"
  local cron="$3"
  local tz="$4"

  echo "Creating scheduler: ${scheduler_name} -> ${job_name} (${cron} ${tz})"

  # Delete existing scheduler if present (idempotent redeploy)
  gcloud scheduler jobs delete "${scheduler_name}" --location "${REGION}" --quiet 2>/dev/null || true

  gcloud scheduler jobs create http "${scheduler_name}" \
    --location "${REGION}" \
    --schedule "${cron}" \
    --time-zone "${tz}" \
    --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_NUMBER}/jobs/${job_name}:run" \
    --http-method POST \
    --oauth-service-account-email "${SERVICE_ACCOUNT}" \
    --oauth-token-scope "https://www.googleapis.com/auth/cloud-platform"
}

# Daily: run at 18:15 LA time (= 02:15 UTC standard / 01:15 UTC daylight)
create_scheduler "ascat-daily-processor"   "ascat-daily-processor"   "15 18 * * *" "America/Los_Angeles"

# Monthly: run on the 3rd of each month at 22:30 LA time (= 06:30 UTC standard / 05:30 UTC daylight)
create_scheduler "ascat-monthly-processor" "ascat-monthly-processor" "30 22 3 * *" "America/Los_Angeles"

# ----------------------------
# Done
# ----------------------------
echo ""
echo "All done."
echo "Image:      ${IMAGE_PATH}"
echo "Jobs:       ascat-daily-processor, ascat-monthly-processor"
echo "Schedulers: ascat-daily-processor (18:15 America/Los_Angeles daily)"
echo "            ascat-monthly-processor (22:30 America/Los_Angeles, 3rd of month)"
