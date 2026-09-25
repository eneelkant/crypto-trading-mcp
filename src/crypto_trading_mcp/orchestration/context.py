from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from crypto_trading_mcp.agents.messages import AgentMessage
from crypto_trading_mcp.config.settings import Settings, get_settings
from crypto_trading_mcp.llm import LLMRouter
from crypto_trading_mcp.market.models import MarketDataService


@dataclass
class ExecutionContext:
    """Shared run context for analytical agents. Never carries exchange secrets."""

    symbol: str
    timeframe: str = "1h"
    exchange_id: str = "kraken"
    settings: Settings = field(default_factory=get_settings)
    market_data: MarketDataService | None = None
    llm_router: LLMRouter | None = None
    messages: dict[str, AgentMessage] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    allow_execution: bool = False

    def store(self, key: str, message: AgentMessage) -> None:
        self.messages[key] = message

    def get(self, key: str) -> AgentMessage | None:
        return self.messages.get(key)

    def require_no_execution(self) -> None:
        if self.allow_execution or self.settings.real_money_enabled:
            raise RuntimeError(
                "Execution is forbidden in the analysis phase. "
                "LIVE_TRADING_ENABLED must remain false."
            )
