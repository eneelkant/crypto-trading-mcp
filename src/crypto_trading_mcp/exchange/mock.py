from __future__ import annotations

from crypto_trading_mcp.exchange.paper import PaperExchange


class MockExchange(PaperExchange):
    """Test-oriented alias of PaperExchange with explicit mock naming."""

    name = "mock"
