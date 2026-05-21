#!/bin/bash
set -euo pipefail

PROJECT_ID="YOUR_PROJECT_ID"
REGION="us-east4"

REPO_NAME="mh1-primprod-processor"
IMAGE_NAME="mh1-primprod-processor"
TAG="v1"

SERVICE_ACCOUNT="YOUR_SERVICE_ACCOUNT@${PROJECT_ID}.iam.gserviceaccount.com"
PLATFORM="${PLATFORM:-linux/amd64}"
IMAGE_PATH="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${IMAGE_NAME}:${TAG}"

JOB_DAILY="mh1-primprod-daily"
JOB_3DAY="mh1-primprod-3day"
JOB_8DAY="mh1-primprod-8day"

need() { command -v "$1" >/dev/null 2>&1 || { echo "Missing required command: $1" >&2; exit 1; }; }
need gcloud
need docker

echo "Using image: ${IMAGE_PATH}"

echo "Building Docker image..."
docker buildx build --platform "${PLATFORM}" -t "${IMAGE_NAME}:${TAG}" --load .

gcloud config set project "${PROJECT_ID}" >/dev/null

if ! gcloud artifacts repositories describe "${REPO_NAME}" --location="${REGION}" >/dev/null 2>&1; then
  gcloud artifacts repositories create "${REPO_NAME}" \
    --repository-format=docker \
    --location="${REGION}" \
    --description="Docker repository for MH1 primary productivity processing"
fi

gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

docker tag "${IMAGE_NAME}:${TAG}" "${IMAGE_PATH}"
docker push "${IMAGE_PATH}"

deploy_job () {
  local JOB_NAME="$1"
  local MODE="$2"

  gcloud run jobs deploy "${JOB_NAME}" \
    --image "${IMAGE_PATH}" \
    --service-account "${SERVICE_ACCOUNT}" \
    --tasks 1 \
    --max-retries 0 \
    --task-timeout "6h" \
    --region "${REGION}" \
    --memory "16Gi" \
    --cpu "4" \
    --set-env-vars "GCS_BUCKET=YOUR_PRODUCTION_BUCKET,LOG_LEVEL=INFO,MODE=${MODE}"
}

echo "Deploying Cloud Run Jobs..."
deploy_job "${JOB_DAILY}" "daily"
deploy_job "${JOB_3DAY}" "composite_3"
deploy_job "${JOB_8DAY}" "composite_8"

echo "Configuring Cloud Scheduler..."
PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"

create_scheduler () {
  local JOB_NAME="$1"
  local SCHEDULE="$2"

  gcloud scheduler jobs delete "${JOB_NAME}" --location "${REGION}" --quiet 2>/dev/null || true
  gcloud scheduler jobs create http "${JOB_NAME}" \
    --location "${REGION}" \
    --schedule "${SCHEDULE}" \
    --time-zone "America/Los_Angeles" \
    --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_NUMBER}/jobs/${JOB_NAME}:run" \
    --http-method POST \
    --oauth-service-account-email "${SERVICE_ACCOUNT}" \
    --oauth-token-scope "https://www.googleapis.com/auth/cloud-platform"
}

# Matches on-prem cron exactly.
create_scheduler "${JOB_DAILY}" "0 12 * * *"
create_scheduler "${JOB_3DAY}" "30 12 * * *"
create_scheduler "${JOB_8DAY}" "35 12 * * *"

echo ""
echo "All done."
echo "Image: ${IMAGE_PATH}"
echo "Jobs:  ${JOB_DAILY}, ${JOB_3DAY}, ${JOB_8DAY}"
echo "Manual triggers:"
echo "  gcloud run jobs execute ${JOB_DAILY} --region=${REGION} --wait"
echo "  gcloud run jobs execute ${JOB_3DAY} --region=${REGION} --wait"
echo "  gcloud run jobs execute ${JOB_8DAY} --region=${REGION} --wait"
