# Trading Stages

`TradingStageManager` default: `STAGE_1_LOCAL_PAPER`.

Stages 0→6. No skipping. No automatic promotion. Evidence + operator required.

Config: `config/trading_stages.yaml`.

Cloud-paper (`STAGE_2`) isolates live via `cloud_paper_isolated` policy flag and `cloud_paper` entrypoint.
