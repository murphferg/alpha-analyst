# AWS Deployment — Alpha Analyst

This directory contains everything needed to deploy Alpha Analyst to AWS using
**ECS Fargate** with an **Application Load Balancer**.

## Architecture

```
Internet
   │
   ▼
┌──────────────────────────────┐
│  Application Load Balancer   │  (public subnets)
│       port 80 / 443         │
└──────────┬───────────────────┘
           │
    ┌──────┴──────┐
    ▼             ▼
┌────────┐  ┌────────┐
│Gateway │  │Gateway │        ← ECS Fargate (private subnets)
│ :8080  │  │ :8080  │
└────────┘  └────────┘

┌────────────┐  ┌────────────┐
│ Ingestion  │  │  RAG Hub   │  ← ECS Fargate (private subnets)
│  (worker)  │  │ (AI agent) │
└────────────┘  └────────────┘
```

### Services Deployed

| Service | Type | Port | Description |
|---------|------|------|-------------|
| **Gateway** | Web API | 8080 | ASP.NET Core API behind ALB |
| **Ingestion** | Background Worker | — | .NET worker service |
| **RAG Hub** | AI Pipeline | — | Multi-agent financial research system |

### AWS Resources Created

- VPC with public/private subnets across 2 AZs
- Internet Gateway + NAT Gateway
- Application Load Balancer (internet-facing)
- ECS Cluster with Container Insights
- 3 ECR repositories (with lifecycle policies)
- 3 Fargate task definitions and services
- IAM roles (task execution + task)
- Secrets Manager secret for Azure credentials
- CloudWatch log groups (30-day retention)

## Prerequisites

1. **AWS CLI v2** installed and configured with credentials
2. **Docker** installed and running
3. **IAM Permissions**: CloudFormation, ECS, ECR, EC2/VPC, ELB, IAM, Secrets Manager, CloudWatch Logs
4. **Azure credentials** for the RAG Hub and VSAI services (stored in Secrets Manager after stack creation)

## Quick Start

### 1. Deploy the infrastructure

```bash
./deploy.sh --stack-only --env production --region us-east-1
```

### 2. Configure Azure secrets

After the stack is created, populate the Secrets Manager secret with your Azure credentials:

```bash
aws secretsmanager put-secret-value \
  --secret-id production/alpha-analyst/azure-credentials \
  --secret-string '{
    "AZURE_OPENAI_ENDPOINT": "https://your-resource.openai.azure.com/",
    "AZURE_OPENAI_API_KEY": "your-key",
    "AZURE_OPENAI_MODEL": "gpt-4.1",
    "AZURE_OPENAI_EMBEDDING_MODEL": "text-embedding-3-small",
    "AZURE_AI_SEARCH_ENDPOINT": "https://your-search.search.windows.net",
    "AZURE_AI_SEARCH_KEY": "your-search-key"
  }'
```

### 3. Build and deploy images

```bash
./deploy.sh --images-only --env production --region us-east-1
```

### 4. Full deploy (infrastructure + images)

```bash
./deploy.sh --env production --region us-east-1
```

## Deploy Script Options

```
Usage: ./deploy.sh [OPTIONS]

Options:
  --env ENV          Environment name (production|staging). Default: production
  --region REGION    AWS region. Default: us-east-1
  --tag TAG          Docker image tag. Default: git short SHA
  --stack-only       Only deploy/update CloudFormation stack
  --images-only      Only build and push Docker images
  -h, --help         Show this help
```

## Staging Environment

Deploy a separate staging environment:

```bash
./deploy.sh --env staging --region us-east-1
```

This creates a completely isolated set of resources (VPC, ALB, ECS cluster, ECR repos, etc.).

## Teardown

Remove all AWS resources:

```bash
./teardown.sh --env production --region us-east-1
```

## Local Docker Testing

From the repository root, build and run the core services locally:

```bash
# Gateway + Ingestion only (no Azure credentials needed)
docker compose up gateway ingestion

# All services (requires Azure credentials in .env)
docker compose --profile full up
```

## Cost Estimates

Approximate monthly cost for a minimal production deployment (us-east-1):

| Resource | Estimate |
|----------|----------|
| NAT Gateway | ~$32/mo + data |
| ALB | ~$16/mo + LCU |
| Fargate (3 tasks, minimal) | ~$30/mo |
| CloudWatch Logs | ~$5/mo |
| ECR storage | ~$1/mo |
| **Total** | **~$85/mo** |

Costs scale with traffic, task count, and log volume.
