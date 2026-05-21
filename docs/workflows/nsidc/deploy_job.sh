#!/bin/bash
set -euo pipefail

# ----------------------------
# SETTINGS — edit these
# ----------------------------
PROJECT_ID="YOUR_PROJECT_ID"
REGION="us-east4"

REPO_NAME="nsidc-cdr-processor"
IMAGE_NAME="nsidc-cdr-processor"
TAG="v1"

SERVICE_ACCOUNT="YOUR_SERVICE_ACCOUNT@${PROJECT_ID}.iam.gserviceaccount.com"

PLATFORM="${PLATFORM:-linux/amd64}"

IMAGE_PATH="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${IMAGE_NAME}:${TAG}"

JOB_DAILY="nsidc-cdr-daily"
JOB_MONTHLY="nsidc-cdr-monthly"

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
    --description="Docker repository for NSIDC CDR processing"
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
echo "Deploying Cloud Run Job: ${JOB_DAILY}..."
gcloud run jobs deploy "${JOB_DAILY}" \
  --image "${IMAGE_PATH}" \
  --service-account "${SERVICE_ACCOUNT}" \
  --tasks 1 \
  --max-retries 0 \
  --task-timeout "2h" \
  --region "${REGION}" \
  --memory "4Gi" \
  --cpu "2" \
  --set-env-vars "GCS_BUCKET=YOUR_PRODUCTION_BUCKET,LOG_LEVEL=INFO,MODE=daily"

echo "Deploying Cloud Run Job: ${JOB_MONTHLY}..."
gcloud run jobs deploy "${JOB_MONTHLY}" \
  --image "${IMAGE_PATH}" \
  --service-account "${SERVICE_ACCOUNT}" \
  --tasks 1 \
  --max-retries 0 \
  --task-timeout "2h" \
  --region "${REGION}" \
  --memory "4Gi" \
  --cpu "2" \
  --set-env-vars "GCS_BUCKET=YOUR_PRODUCTION_BUCKET,LOG_LEVEL=INFO,MODE=monthly"

# ----------------------------
# 5) Cloud Scheduler
# ----------------------------
echo "Configuring Cloud Scheduler..."

PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"

# Daily: every day at 10:00 PST (NSIDC typically posts by mid-morning UTC)
gcloud scheduler jobs delete "${JOB_DAILY}" --location "${REGION}" --quiet 2>/dev/null || true
gcloud scheduler jobs create http "${JOB_DAILY}" \
  --location "${REGION}" \
  --schedule "0 10 * * *" \
  --time-zone "America/Los_Angeles" \
  --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_NUMBER}/jobs/${JOB_DAILY}:run" \
  --http-method POST \
  --oauth-service-account-email "${SERVICE_ACCOUNT}" \
  --oauth-token-scope "https://www.googleapis.com/auth/cloud-platform"

# Monthly: 09:00 PST on 5th and 15th (same cadence as LEO monthly)
gcloud scheduler jobs delete "${JOB_MONTHLY}" --location "${REGION}" --quiet 2>/dev/null || true
gcloud scheduler jobs create http "${JOB_MONTHLY}" \
  --location "${REGION}" \
  --schedule "0 9 5,15 * *" \
  --time-zone "America/Los_Angeles" \
  --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_NUMBER}/jobs/${JOB_MONTHLY}:run" \
  --http-method POST \
  --oauth-service-account-email "${SERVICE_ACCOUNT}" \
  --oauth-token-scope "https://www.googleapis.com/auth/cloud-platform"

echo ""
echo "All done."
echo "Image:        ${IMAGE_PATH}"
echo "Jobs:         ${JOB_DAILY}, ${JOB_MONTHLY}"
echo "Schedulers:"
echo "  ${JOB_DAILY}    — 10:00 America/Los_Angeles daily"
echo "  ${JOB_MONTHLY}  — 09:00 America/Los_Angeles, 5th and 15th of month"
echo ""
echo "Manual triggers:"
echo "  gcloud run jobs execute ${JOB_DAILY} --region=${REGION} --wait"
echo "  gcloud run jobs execute ${JOB_MONTHLY} --region=${REGION} --wait"
echo ""
echo "Backfill examples:"
echo "  gcloud run jobs execute ${JOB_DAILY} --region=${REGION} --wait \\"
echo "    --update-env-vars START_DATE=2025-01-01,END_DATE=2025-01-31"
echo "  gcloud run jobs execute ${JOB_MONTHLY} --region=${REGION} --wait \\"
echo "    --update-env-vars START_DATE=2024-01-01,END_DATE=2024-12-01"