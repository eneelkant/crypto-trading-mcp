# MCP Tools

MCP server: `python -m crypto_trading_mcp` (`src/crypto_trading_mcp/server.py`).

Surfaces:

- Phase 4 analysis / risk helpers (`mcp_tools/phase4.py`)
- Phase 5 paper trading (`mcp_tools/paper.py`) — no live `execute_trade`
- Phase 6 backtests (`mcp_tools/backtest.py`)
- Phase 8 learning (`mcp_tools/learning.py`)

Learning tools include `get_learning_status`, `get_learning_memory`,
`search_learning_memory`, `get_trade_postmortem`, `get_failure_patterns`,
`get_success_patterns`, `get_calibration`, `get_brier_score`, `get_model_status`,
`get_model_versions`, `get_learning_proposals`, `get_champion_strategy`,
`get_challenger_strategy`, `run_postmortem`, `run_reflection`, `run_retraining`,
`run_learning_validation`, `get_learning_audit`, `rollback_learning_candidate`.

No MCP tool may bypass RiskEngine, Kill Switch, or enable live trading.
