# Disaster Recovery

- Backup Postgres volumes daily (Stage 2+)
- Store stage manager history and order intent ledger off-box
- Kill switch durable flag in DB/object storage for remote halt
- RTO/RPO documented per environment; cold standby optional until Stage 6
