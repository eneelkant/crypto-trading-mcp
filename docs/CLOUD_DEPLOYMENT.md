# Cloud Deployment

Recommended progression: local paper → GCE/EC2 Docker Compose cloud-paper → externalize Postgres → Stage 3 read-only secrets → later GKE/EKS if needed.

Artifacts:
- `deploy/Dockerfile`
- `deploy/docker-compose.cloud-paper.yml`
- entrypoint `python -m crypto_trading_mcp.cloud_paper`

Cloud-paper enforces paper mode and refuses live gate approval.
