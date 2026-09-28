# Cloud 24×7 Architecture

**Audit only. Live trading remains disabled. No cloud deployment is performed by this document.**

```text
TRADING_MODE=paper
LIVE_TRADING_ENABLED=false
```

Goal of Stage 2: run **continuous paper trading** safely in the cloud before any real capital path.

---

## 1. Application characteristics (drive hosting choice)

| Characteristic | Implication |
|----------------|-------------|
| Long-running autonomous loop + optional WebSocket | Needs **always-on process**, not request-only FaaS |
| In-process thread loop (`AutonomousPaperLoop`) | Sticky single worker unless redesigned as job queue |
| Local file state (`.runtime/`, optional STOP file) | Needs **persistent volume** or external store |
| Dashboard EventBus in-memory | Needs sticky instance or external event bus |
| Public market data polling | Outbound HTTPS; rate limits |
| Future exchange WS | Persistent egress, reconnect loops |
| Kill switch / halt | Must work when operator is offline (file, API, alert) |
| Secrets for Stage 3+ | Secret manager + stable egress IP for allowlists |
| Python 3.12 app + optional Node dashboard UI | Container-friendly |

**Cloud Run (request-scaled, CPU often idle when no requests) is a poor default** for an
always-on trading loop unless min-instances=1, CPU always allocated, and externalized
state — still awkward for WS. Prefer a **VM or Kubernetes Deployment** for Stage 2+.

---

## 2. Required building blocks

| Component | Stage 2 (cloud paper) | Stage 5 (live) |
|-----------|----------------------|----------------|
| Application server | Container running `trader` / loop + optional API | Same + stricter gates |
| Database | Postgres (sessions, orders, fills, learning) | Same + stronger backups |
| Cache | Optional Redis (market cache, locks) | Redis for idempotency locks |
| Scheduler | Loop interval + cron for reports | Same + reconciliation cron |
| WebSocket | Optional market WS client | Required for low-latency venues |
| Secret manager | LLM keys if used | Exchange + LLM |
| Monitoring | Metrics + logs | + pages for P0 alerts |
| Health checks | `/health` process + loop heartbeat | + exchange connectivity |
| Auto restart | systemd / k8s restartPolicy | Same |
| Backup | DB snapshots | DB + config + runbooks |
| DR | Cold standby region later | Documented RTO/RPO |
| Kill switch | STOP via API + object storage flag | Cancels open live orders |
| Deploy | Immutable images, staged env | Promotion gates Stage 0→6 |

---

## 3. Option comparison (requirements-based)

### A. Google Cloud Run

| Pros | Cons |
|------|------|
| Simple deploy, managed TLS | Not natural for always-on WS loops |
| Scales to zero (cost) | Scale-to-zero **breaks** 24×7 trading |
| Good with Secret Manager | Needs min instances + CPU always-on ≈ VM cost |
| | Ephemeral filesystem unless networked storage |

**Fit:** Weak for Stage 2 loop unless heavily customized. Better for **stateless APIs**
(dashboard read replicas), not the trading worker.

### B. Google Compute Engine (or AWS EC2)

| Pros | Cons |
|------|------|
| Always-on; simple mental model | More ops (patching, disk) |
| Persistent disk for `.runtime` during migration | Single VM = single AZ risk |
| Static IP / Cloud NAT for exchange allowlists | Manual HA |
| systemd restart of worker | |

**Fit:** **Strong for Stage 2** early cloud paper. Lowest complexity to match current
process model.

### C. Google Kubernetes Engine (or AWS EKS)

| Pros | Cons |
|------|------|
| Restarts, probes, rolling deploys | Higher complexity/cost |
| Sidecars for metrics/secrets | Overkill before state externalized |
| Horizontal patterns later | Need careful singleton for order workers |

**Fit:** **Strong for Stage 5–6** once DB/Redis/idempotency are externalized and
exactly-once order intent is designed. Premature as first cloud step.

### D. Simple VPS (non-hyperscaler)

| Pros | Cons |
|------|------|
| Cheap, always-on | Weaker IAM/secret manager story |
| Easy SSH ops | You own security updates entirely |
| | Harder compliance/audit trail |

**Fit:** Acceptable for **personal Stage 2 paper** if patched and firewalled; weaker for
production live capital.

### E. AWS equivalents (summary)

| GCP | AWS |
|-----|-----|
| Cloud Run | App Runner / ECS Fargate (still awkward for WS) |
| Compute Engine | EC2 |
| GKE | EKS |
| Secret Manager | Secrets Manager |
| Cloud NAT | NAT Gateway |
| Cloud Monitoring | CloudWatch |

Choice between GCP and AWS should follow **existing org identity, networking, and
secret posture**, not framework preference.

---

## 4. Recommended progression

```text
Stage 1 local paper
  → Stage 2: single GCE/EC2 (or small VPS) + Docker Compose
       Postgres + worker + dashboard (localhost/VPN)
  → Externalize state (DB/Redis)
  → Stage 3 read-only keys via Secret Manager + NAT IP allowlist
  → Stage 4 dry-run validation
  → Stage 5 tiny live on same singleton worker
  → Stage 6: consider GKE/EKS only if HA/multi-service justified
```

---

## 5. Reference Stage 2 topology

```text
[Operator VPN / IAP]
        │
   Dashboard :8050 (auth later)
        │
Trading VM / node
  ├── worker: AutonomousPaperLoop (paper only)
  ├── mcp/cli optional
  ├── Postgres (sessions, events, learning)
  ├── STOP flag (file or DB row) + alert webhook
  └── node_exporter / structured logs → Monitoring
        │
   Egress NAT (static)
        │
   Public market data APIs (Kraken/CCXT, etc.)
```

**Do not** bind dashboard to `0.0.0.0` without authentication.

---

## 6. Gaps in current repo for 24×7 cloud

1. No Dockerfile / compose / Helm (absent).
2. Default paper store is in-memory; `.runtime` JSON is not multi-instance safe.
3. No production `/health`/`/ready` contract for orchestrators (dashboard health exists).
4. No log shipping / metrics exporters.
5. No automated backup.
6. Kill switch is local `STOP` file — needs remote durable equivalent.
7. WebSocket market feed not productionized.
8. No IaC (Terraform) for NAT + secrets + VM.

---

## 7. Monitoring & alerting (minimum)

| Signal | Severity |
|--------|----------|
| Loop heartbeat missing | P0 |
| Kill switch active | P0 |
| Stale market data > threshold | P0/P1 |
| Exchange API error rate | P1 |
| Daily loss limit approached | P0 (live) / P1 (paper) |
| Disk / DB full | P1 |
| Process crash loop | P0 |

---

## 8. Readiness

| Item | Status |
|------|--------|
| Always-on loop code | Partial (local) |
| Cloud packaging | Missing |
| Durable state | Missing |
| Secrets in cloud | Missing |
| Alerting | Missing |

**Cloud readiness: NOT READY (Stage 2 packaging outstanding).**
