#!/usr/bin/env bash
set -euo pipefail

# ── Alpha Analyst — AWS Teardown Script ──
#
# Deletes the CloudFormation stack and all associated resources.
# ECR images must be deleted before stack deletion if repos are non-empty.
#
# Usage:
#   ./teardown.sh [--env staging|production] [--region us-east-1]

ENVIRONMENT="${ENVIRONMENT:-production}"
AWS_REGION="${AWS_REGION:-us-east-1}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)    ENVIRONMENT="$2"; shift 2 ;;
    --region) AWS_REGION="$2"; shift 2 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

STACK_NAME="${ENVIRONMENT}-alpha-analyst"

log() { echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] $*"; }

log "Tearing down stack: $STACK_NAME in $AWS_REGION"

for repo in "${ENVIRONMENT}/alpha-analyst-gateway" "${ENVIRONMENT}/alpha-analyst-ingestion" "${ENVIRONMENT}/alpha-analyst-rag-hub"; do
  log "Deleting images in ECR repo: $repo"
  IMAGE_IDS=$(aws ecr list-images --repository-name "$repo" --region "$AWS_REGION" --query 'imageIds[*]' --output json 2>/dev/null || echo "[]")
  if [ "$IMAGE_IDS" != "[]" ] && [ -n "$IMAGE_IDS" ]; then
    aws ecr batch-delete-image --repository-name "$repo" --region "$AWS_REGION" --image-ids "$IMAGE_IDS" || true
  fi
done

log "Deleting CloudFormation stack"
aws cloudformation delete-stack --stack-name "$STACK_NAME" --region "$AWS_REGION"

log "Waiting for stack deletion..."
aws cloudformation wait stack-delete-complete --stack-name "$STACK_NAME" --region "$AWS_REGION"

log "Teardown complete"
