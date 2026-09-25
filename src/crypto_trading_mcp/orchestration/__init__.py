"""Orchestration package."""

__all__ = [
    "ExecutionContext",
    "StateMachine",
    "TradingOrchestrator",
    "TradingState",
    "build_test_orchestrator",
]


def __getattr__(name: str):
    if name == "ExecutionContext":
        from crypto_trading_mcp.orchestration.context import ExecutionContext

        return ExecutionContext
    if name in {"StateMachine", "TradingState"}:
        from crypto_trading_mcp.orchestration import state_machine as sm

        return getattr(sm, name)
    if name in {"TradingOrchestrator", "build_test_orchestrator"}:
        from crypto_trading_mcp.orchestration import orchestrator as orch

        return getattr(orch, name)
    raise AttributeError(name)
