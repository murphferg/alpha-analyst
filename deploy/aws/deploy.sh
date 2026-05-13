#!/usr/bin/env bash
set -euo pipefail

# ── Alpha Analyst — AWS Deployment Script ──
#
# Usage:
#   ./deploy.sh [--stack-only | --images-only] [--env staging|production] [--region us-east-1]
#
# Prerequisites:
#   - AWS CLI v2 configured with appropriate credentials
#   - Docker installed and running
#   - Sufficient IAM permissions for CloudFormation, ECR, ECS, VPC, ALB, IAM, Secrets Manager, CloudWatch

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

ENVIRONMENT="${ENVIRONMENT:-production}"
AWS_REGION="${AWS_REGION:-us-east-1}"
STACK_NAME=""
IMAGE_TAG="${IMAGE_TAG:-$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo 'latest')}"
DEPLOY_STACK=true
DEPLOY_IMAGES=true

usage() {
  echo "Usage: $0 [OPTIONS]"
  echo ""
  echo "Options:"
  echo "  --env ENV          Environment name (production|staging). Default: production"
  echo "  --region REGION    AWS region. Default: us-east-1"
  echo "  --tag TAG          Docker image tag. Default: git short SHA"
  echo "  --stack-only       Only deploy/update CloudFormation stack"
  echo "  --images-only      Only build and push Docker images"
  echo "  -h, --help         Show this help"
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)       ENVIRONMENT="$2"; shift 2 ;;
    --region)    AWS_REGION="$2"; shift 2 ;;
    --tag)       IMAGE_TAG="$2"; shift 2 ;;
    --stack-only)  DEPLOY_IMAGES=false; shift ;;
    --images-only) DEPLOY_STACK=false; shift ;;
    -h|--help)   usage ;;
    *) echo "Unknown option: $1"; usage ;;
  esac
done

STACK_NAME="${ENVIRONMENT}-alpha-analyst"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text --region "$AWS_REGION")

log() { echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] $*"; }

# ── Deploy CloudFormation stack ──
deploy_stack() {
  log "Deploying CloudFormation stack: $STACK_NAME"

  aws cloudformation deploy \
    --template-file "$SCRIPT_DIR/cloudformation.yaml" \
    --stack-name "$STACK_NAME" \
    --region "$AWS_REGION" \
    --capabilities CAPABILITY_IAM \
    --parameter-overrides \
      EnvironmentName="$ENVIRONMENT" \
      GatewayImageTag="$IMAGE_TAG" \
      IngestionImageTag="$IMAGE_TAG" \
      RagHubImageTag="$IMAGE_TAG" \
    --no-fail-on-empty-changeset

  log "Stack outputs:"
  aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$AWS_REGION" \
    --query "Stacks[0].Outputs" \
    --output table
}

# ── Build and push Docker images ──
build_and_push() {
  log "Authenticating Docker with ECR in $AWS_REGION"
  aws ecr get-login-password --region "$AWS_REGION" \
    | docker login --username AWS --password-stdin \
      "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

  local services=(
    "gateway:src/AlphaAnalyst.Gateway:${ENVIRONMENT}/alpha-analyst-gateway"
    "ingestion:src/AlphaAnalyst.Ingestion:${ENVIRONMENT}/alpha-analyst-ingestion"
    "rag-hub:src/alpha_analyst_rag_hub:${ENVIRONMENT}/alpha-analyst-rag-hub"
  )

  for entry in "${services[@]}"; do
    IFS=: read -r name context repo <<< "$entry"
    local full_image="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${repo}"

    log "Building $name from $context"
    docker build -t "${full_image}:${IMAGE_TAG}" -t "${full_image}:latest" \
      -f "$REPO_ROOT/$context/Dockerfile" "$REPO_ROOT/$context"

    log "Pushing $name"
    docker push "${full_image}:${IMAGE_TAG}"
    docker push "${full_image}:latest"
  done
}

# ── Update ECS services to use new images ──
update_services() {
  log "Forcing new deployment for ECS services"
  local cluster="${ENVIRONMENT}-alpha-analyst"

  for svc in gateway ingestion rag-hub; do
    log "Updating service: $svc"
    aws ecs update-service \
      --cluster "$cluster" \
      --service "$svc" \
      --force-new-deployment \
      --region "$AWS_REGION" \
      --query "service.serviceName" \
      --output text
  done

  log "Waiting for gateway service to stabilize..."
  aws ecs wait services-stable \
    --cluster "$cluster" \
    --services gateway \
    --region "$AWS_REGION" || log "Warning: timed out waiting for stabilization"
}

# ── Main ──
log "Alpha Analyst AWS Deploy"
log "  Environment : $ENVIRONMENT"
log "  Region      : $AWS_REGION"
log "  Image tag   : $IMAGE_TAG"
log "  Account     : $AWS_ACCOUNT_ID"

if $DEPLOY_STACK; then
  deploy_stack
fi

if $DEPLOY_IMAGES; then
  build_and_push
  update_services
fi

log "Deployment complete!"

if $DEPLOY_STACK; then
  GATEWAY_URL=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$AWS_REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='GatewayURL'].OutputValue" \
    --output text)
  log "Gateway API: $GATEWAY_URL"
fi
