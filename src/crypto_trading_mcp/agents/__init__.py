"""Agent framework package."""

__all__ = [
    "AgentMessage",
    "AgentRegistry",
    "BaseAgent",
    "Decision",
    "MessageStatus",
    "build_default_registry",
]


def __getattr__(name: str):
    if name in {"AgentMessage", "Decision", "MessageStatus"}:
        from crypto_trading_mcp.agents import messages as messages_mod

        return getattr(messages_mod, name)
    if name == "BaseAgent":
        from crypto_trading_mcp.agents.base import BaseAgent

        return BaseAgent
    if name in {"AgentRegistry", "build_default_registry"}:
        from crypto_trading_mcp.agents import registry as registry_mod

        return getattr(registry_mod, name)
    raise AttributeError(name)
