# Phase 5 — AWS Production Deployment

Start Phase 5 only after Phase 4 (Adaptive RAG) is complete and validated.

## AWS Services (all ap-southeast-2 / Sydney)

| Service | Purpose | Config |
|---|---|---|
| ECS Fargate | App hosting | 2 tasks, 1 vCPU / 2GB each |
| RDS PostgreSQL 16 | pgvector database | db.t3.medium, private subnet, 7-day backups |
| S3 | PDF storage | AES-256 encryption, no public access |
| API Gateway (HTTP) | Public entrypoint | HTTPS only, per-tenant throttling |
| Secrets Manager | Credentials | OPENAI_API_KEY, DATABASE_URL, ADMIN_API_KEY |
| ECR | Docker image registry | — |
| CloudWatch | Logs + metrics | Structured log groups per service |
| ALB | Load balancer | HTTP → ECS target group |

## Data Sovereignty

All infrastructure in `ap-southeast-2`. EA tenant requires `data_sovereignty: "AU"` in config.

When `data_sovereignty: "AU"`:
- Use `bedrock_provider.py` not `openai_provider.py`
- Bedrock models: `anthropic.claude-haiku-4-5` (generation), `amazon.titan-embed-text-v2` (embeddings)
- OpenAI API must not be called for this tenant

## Build Order (Phase 5)

1. **Containerise** — Dockerfile multi-stage build, verify locally with docker-compose
2. **AWS infra** — S3, RDS (with pgvector), ECR, ECS cluster, ALB, API Gateway
3. **Secrets** — move all secrets to Secrets Manager, update app to load from SM in production
4. **CI/CD** — GitHub Actions: test → docker build → ECR push → ECS rolling deploy
5. **Bedrock provider** — implement `bedrock_provider.py`, migrate EA tenant, verify sovereignty
6. **Monitoring** — CloudWatch dashboards, alerts (error rate >5%, P99 latency >10s)

## Cost Estimate (initial)

| Resource | Monthly est. |
|---|---|
| ECS Fargate (2 tasks) | ~$60 |
| RDS db.t3.medium | ~$55 |
| S3 (50GB) | ~$2 |
| API Gateway | ~$10 |
| **Total** | **~$130/month** |

Scale RDS to db.t3.large (~$110/month) when tenant count exceeds 10.

## IAM Policy for ECS Task Role (least privilege)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::rag-system-docs-prod/tenants/*"
    },
    {
      "Effect": "Allow",
      "Action": ["secretsmanager:GetSecretValue"],
      "Resource": "arn:aws:secretsmanager:ap-southeast-2:*:secret:rag-system/*"
    },
    {
      "Effect": "Allow",
      "Action": ["bedrock:InvokeModel"],
      "Resource": "*"
    }
  ]
}
```

## Bedrock Provider

`app/core/providers/bedrock_provider.py` (currently a stub) must implement `BaseLLMProvider`:

- **Generation model:** `anthropic.claude-haiku-4-5` via `bedrock-runtime` `converse` API
- **Embedding model:** `amazon.titan-embed-text-v2:0` (1536 dims — matches existing pgvector index)
- **Auth:** ECS task role (no access keys in env); `boto3.client("bedrock-runtime", region_name="ap-southeast-2")`
- **Routing:** `app/dependencies.py` `get_provider()` already checks `tenant.config["data_sovereignty"]` — just make BedrockProvider functional

## Monitoring

CloudWatch dashboards to create:

| Metric | Alert threshold |
|---|---|
| API 5xx error rate | >5% over 5 min |
| P99 chat latency | >10s |
| Ingest job failure rate | >10% over 15 min |
| RDS CPU | >80% over 10 min |
| ECS task count | <2 tasks running |

Structured logs already emitted by the app (`logger.info` with `extra={}` dicts) — set up CloudWatch metric filters on `level=ERROR` and `agent.generate` latency fields.
