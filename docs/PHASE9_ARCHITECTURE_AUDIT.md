Phase 9 Architecture Audit

Phase 8 baseline: PASS (main @ c8c0d9f)

Existing reusable components:
- ExchangeAdapter ABC, PaperExchange, MockExchange, LiveExecutionBlocked stubs
- PublicCCXTMarketData (REST public OHLCV/ticker/orderbook)
- RiskEngine, KillSwitch, Portfolio, TradePlanner, PaperTradingEngine
- 16-agent registry, orchestrator, proposal pipeline, StateMachine
- LLM Mock/Ollama/OpenAI/Anthropic/Gemini providers
- LearningEngine, EventBus, dashboard, CLI, MCP tools, persistence
- Backtest/WalkForward engines

Missing components:
- Unified MarketDataGateway (WS/REST/cache/health/stale)
- Production Coinbase/Delta adapters (HMAC, retries) beyond stubs
- Continuous autonomous paper cycle runner with cycle IDs
- Order idempotency keys
- Cycle-oriented state machine events
- production_trading / market_data / exchanges / autonomous_loop configs

Components requiring hardening:
- ExchangeAdapter method surface (account/balances/history aliases)
- factory live-name resolution for public/read adapters without enabling live orders
- StateMachine transitions for EXECUTING→FILLED path (paper only)
- LLM failure → NO NEW TRADE in continuous loop

Duplicate functionality to avoid:
- Do not fork PaperExchange / RiskEngine / LearningEngine / Dashboard
- Do not create a second walk-forward or EventBus

Market-data readiness: Partial (public CCXT REST exists; need gateway/normalize/stale/WS hooks)
Exchange-adapter readiness: Partial (stubs only for Coinbase/Delta)
Continuous-loop readiness: Partial (one-shot demo cycle exists; need persistent runner)
LLM-provider readiness: Good (providers present; wire into cycle timeouts)
Risk/safety readiness: Strong (keep live gate + kill switch authoritative)
Persistence/recovery readiness: Partial (paper store; add cycle state snapshot)
Observability readiness: Good (extend EventBus with cycle events)

Recommended implementation sequence:
1 configs → 2 market gateway → 3 exchange harden + Coinbase/Delta → 4 continuous loop
→ 5 idempotency → 6 CLI/MCP → 7 tests/docs

Expected files to change:
- src/crypto_trading_mcp/market/{base,gateway,normalizer,websocket,rest,health,cache}.py
- src/crypto_trading_mcp/exchange/{base,coinbase,delta_india,health,auth,factory}.py
- src/crypto_trading_mcp/autonomous/ (new)
- config/{production_trading,market_data,exchanges,autonomous_loop}.yaml
- cli/trader.py, server.py, mcp_tools/, dashboard/events.py
- tests/unit|integration|safety/phase9/
- docs/PHASE9.md and related
