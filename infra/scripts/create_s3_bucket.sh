#!/usr/bin/env bash

set -euo pipefail

BUCKET_NAME="${1:-stimpactai-artifacts-dev}"
AWS_REGION="${2:-us-west-2}"

if [[ "${AWS_REGION}" == "us-east-1" ]]; then
  aws s3api create-bucket --bucket "${BUCKET_NAME}" --region "${AWS_REGION}"
else
  aws s3api create-bucket \
    --bucket "${BUCKET_NAME}" \
    --region "${AWS_REGION}" \
    --create-bucket-configuration "LocationConstraint=${AWS_REGION}"
fi

aws s3api put-bucket-versioning \
  --bucket "${BUCKET_NAME}" \
  --versioning-configuration Status=Enabled

echo "Created and versioned s3://${BUCKET_NAME}"
