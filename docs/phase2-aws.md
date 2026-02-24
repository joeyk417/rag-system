# Phase 2 — AWS Production Deployment

Start Phase 2 only after all Phase 1 validation queries pass locally.

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

## Build Order (Phase 2)

1. **Containerise** — Dockerfile multi-stage build, verify locally with docker-compose
2. **AWS infra** — S3, RDS (with pgvector), ECR, ECS cluster, ALB, API Gateway
3. **Secrets** — move all secrets to Secrets Manager, update app to load from SM in production
4. **CI/CD** — GitHub Actions: test → docker build → ECR push → ECS rolling deploy
5. **Bedrock provider** — implement `bedrock_provider.py`, migrate EA tenant, verify sovereignty
6. **Self-RAG agent** — hallucination detection + answer quality grading (Notebook 06 pattern)
7. **Adaptive RAG agent** — multi-source routing: vector docs / web search (Notebook 07 pattern)
8. **Monitoring** — CloudWatch dashboards, alerts (error rate >5%, P99 latency >10s)

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

## Phase 2 Agent Upgrade: Self-RAG

```
START → retrieve → grade_documents →
    [irrelevant] → transform_query → retrieve (loop)
    [relevant]   → generate →
        [hallucinating]     → generate (retry)
        [grounded, bad]     → transform_query → retrieve (loop)
        [grounded, good]    → END
```

## Phase 2 Agent Upgrade: Adaptive RAG

```
START → route_question →
    [financial docs]   → retrieve → grade → generate → END (Self-RAG flow)
    [web/general]      → web_search_agent → END
    [future: SQL]      → sql_agent → END
```

Routing decision uses LLM structured output against `RouterQuery` schema. Tenant config controls which routes are enabled.
