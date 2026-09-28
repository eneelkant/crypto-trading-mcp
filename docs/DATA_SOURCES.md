# Data Sources

`DataSourceAdapter` + `SourceCategory`:

MARKET_DATA, FUNDAMENTAL_DATA, NEWS, SOCIAL, ON_CHAIN, MACRO, RESEARCH, INTERNAL_MEMORY, PREDICTION_MARKET

Each `IntelligenceRecord` carries source_id, type, timestamps, freshness, confidence, provenance, content, metadata, status.

Unavailable providers fail closed and refuse fabrication.
