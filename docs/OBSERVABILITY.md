# Observability

Structured events flow through `EventBus` and are streamed over `/ws`.

Event examples: `AgentStarted`, `StrategySignalGenerated`, `ConsensusGenerated`,
`RiskApproved`, `OrderFilled`, `PortfolioUpdated`, `BacktestCompleted`,
`KillSwitchActivated`.

## Principles

- Factual structured summaries only
- No private chain-of-thought
- No credentials in logs/events
- Dashboard failure must not stop trading
- Live trading cannot be enabled from the UI

Learning events: `LearningStarted`, `TradePostmortemCompleted`, `BrierUpdated`,
`CalibrationUpdated`, `DriftDetected`, `ReflectionCompleted`, `ChallengerValidated`,
`LearningProposalCreated`, etc.
