Read CLAUDE.md, docs/phase5-aws.md, and MEMORY.md for current project state.

Phase 4 (Adaptive RAG) must be complete before starting Phase 5.

Then start Phase 5 — AWS Production Deployment — completing sub-tasks in order:
1. Phase 5-1 Containerise: Dockerfile multi-stage build, verify with docker compose
2. Phase 5-2 AWS infra: S3, RDS pgvector, ECR, ECS Fargate, ALB, API Gateway (ap-southeast-2)
3. Phase 5-3 Secrets: move all secrets to AWS Secrets Manager
4. Phase 5-4 CI/CD: GitHub Actions — test → docker build → ECR push → ECS rolling deploy
5. Phase 5-5 Bedrock provider: implement bedrock_provider.py, migrate EA tenant (data_sovereignty=AU)
6. Phase 5-6 Monitoring: CloudWatch dashboards + alerts (error rate >5%, P99 latency >10s)

Ask before making any assumptions not covered in CLAUDE.md or docs/phase5-aws.md.
