from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import ccxt
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

mcp = FastMCP(
    "Crypto Trading MCP",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[
            "127.0.0.1:*",
            "localhost:*",
        ],
    ),
)


def _exchange(exchange_id: str) -> Any:
    exchange_name = exchange_id.lower()
    if exchange_name not in ccxt.exchanges:
        raise ValueError(f"Unsupported exchange: {exchange_id}")

    return getattr(ccxt, exchange_name)({"enableRateLimit": True})


@mcp.tool()
def get_spot_price(symbol: str, exchange_id: str = "kraken") -> dict[str, Any]:
    """Return the latest public spot-market price for an exchange symbol such as BTC/USD."""
    exchange = _exchange(exchange_id)

    try:
        ticker = exchange.fetch_ticker(symbol.upper())
    except ccxt.BaseError as error:
        raise ValueError(
            f"Could not fetch {symbol.upper()} from {exchange_id}: {error}"
        ) from error

    return {
        "exchange": exchange_id.lower(),
        "symbol": ticker["symbol"],
        "last_price": ticker["last"],
        "bid": ticker["bid"],
        "ask": ticker["ask"],
        "quote_volume": ticker["quoteVolume"],
        "fetched_at": datetime.now(UTC).isoformat(),
        "note": "Public market data only; this tool does not place trades.",
    }


@mcp.tool()
def estimate_swap_profit(
    asset_amount: float,
    entry_price_usd: float,
    exit_price_usd: float,
    entry_fee_percent: float = 0.0,
    exit_fee_percent: float = 0.0,
    network_fee_usd: float = 0.0,
) -> dict[str, float | str]:
    """Estimate USD profit or loss after trading and network fees. This is not investment advice."""
    values = [
        asset_amount,
        entry_price_usd,
        exit_price_usd,
        entry_fee_percent,
        exit_fee_percent,
        network_fee_usd,
    ]
    if any(value < 0 for value in values):
        raise ValueError("Amounts, prices, and fees must be zero or greater.")
    if entry_price_usd == 0:
        raise ValueError("entry_price_usd must be greater than zero.")
    if entry_fee_percent >= 100 or exit_fee_percent >= 100:
        raise ValueError("Percentage fees must be below 100.")

    gross_cost = asset_amount * entry_price_usd
    entry_fee_usd = gross_cost * (entry_fee_percent / 100)
    gross_proceeds = asset_amount * exit_price_usd
    exit_fee_usd = gross_proceeds * (exit_fee_percent / 100)
    total_cost = gross_cost + entry_fee_usd + network_fee_usd
    net_proceeds = gross_proceeds - exit_fee_usd
    profit_usd = net_proceeds - total_cost
    profit_percent = (profit_usd / total_cost * 100) if total_cost else 0.0

    return {
        "gross_cost_usd": round(gross_cost, 2),
        "net_proceeds_usd": round(net_proceeds, 2),
        "total_fees_usd": round(entry_fee_usd + exit_fee_usd + network_fee_usd, 2),
        "profit_usd": round(profit_usd, 2),
        "profit_percent": round(profit_percent, 2),
        "disclaimer": "Estimate only; prices, slippage, and fees can change before execution.",
    }


# --- Phase 5 paper-safe tools (no live execute_trade) ---
_paper_tools = None


def _paper():
    global _paper_tools
    if _paper_tools is None:
        from crypto_trading_mcp.mcp_tools.paper import PaperToolSurface

        _paper_tools = PaperToolSurface()
    return _paper_tools


@mcp.tool()
def get_portfolio() -> dict[str, Any]:
    """Return the paper portfolio snapshot. Real money is never used."""
    return _paper().get_portfolio()


@mcp.tool()
def get_positions() -> list[dict[str, Any]]:
    """Return open paper positions."""
    return _paper().get_positions()


@mcp.tool()
def get_open_orders() -> list[dict[str, Any]]:
    """Return open paper orders."""
    return _paper().get_open_orders()


@mcp.tool()
def get_trade_status(order_id: str) -> dict[str, Any]:
    """Return status for a paper order id."""
    return _paper().get_trade_status(order_id)


@mcp.tool()
def get_performance() -> dict[str, Any]:
    """Return paper trading performance metrics."""
    return _paper().get_performance()


@mcp.tool()
def propose_trade(plan: dict[str, Any]) -> dict[str, Any]:
    """Acknowledge a proposed trade plan (no execution)."""
    return _paper().propose_trade(plan)


@mcp.tool()
def validate_trade(plan: dict[str, Any]) -> dict[str, Any]:
    """Validate a trade for paper mode. Does not place live orders."""
    return _paper().validate_trade(plan)


@mcp.tool()
def paper_execute_trade(plan: dict[str, Any], market_price: float) -> dict[str, Any]:
    """Execute a trade on the PaperExchange only when TRADING_MODE=paper."""
    from crypto_trading_mcp.config.settings import get_settings

    settings = get_settings()
    if settings.trading_mode != "paper":
        return {
            "executed": False,
            "reason_codes": ["TRADING_MODE_NOT_PAPER"],
            "note": "paper_execute_trade refuses non-paper modes.",
        }
    if settings.live_trading_enabled:
        return {
            "executed": False,
            "reason_codes": ["LIVE_TRADING_ENABLED_BLOCKED"],
        }
    return _paper().paper_execute_trade(plan, market_price)


@mcp.tool()
def run_paper_trade(plan: dict[str, Any], market_price: float) -> dict[str, Any]:
    """Alias for paper_execute_trade. Simulated capital only."""
    return paper_execute_trade(plan, market_price)


@mcp.tool()
def get_paper_status() -> dict[str, Any]:
    """Paper trading engine status."""
    return _paper().get_paper_status()


@mcp.tool()
def get_paper_orders() -> list[dict[str, Any]]:
    """Open paper orders."""
    return _paper().get_paper_orders()


@mcp.tool()
def get_paper_trades() -> list[dict[str, Any]]:
    """Completed paper trades."""
    return _paper().get_paper_trades()


@mcp.tool()
def get_paper_portfolio() -> dict[str, Any]:
    """Paper portfolio snapshot."""
    return _paper().get_paper_portfolio()


@mcp.tool()
def get_paper_performance() -> dict[str, Any]:
    """Paper performance metrics."""
    return _paper().get_paper_performance()


@mcp.tool()
def reset_paper_account() -> dict[str, Any]:
    """Reset the local paper account (simulated capital only)."""
    return _paper().reset_paper_account()


# --- Phase 6 backtest tools (simulation / read-only) ---
_backtest_tools = None


def _backtest():
    global _backtest_tools
    if _backtest_tools is None:
        from crypto_trading_mcp.mcp_tools.backtest import BacktestToolSurface

        _backtest_tools = BacktestToolSurface()
    return _backtest_tools


@mcp.tool()
def run_backtest(
    symbol: str,
    strategy_id: str = "momentum_breakout_crypto",
    timeframe: str = "1h",
    bars: int = 120,
) -> dict[str, Any]:
    """Run an offline historical backtest via PaperExchange. Never places live orders."""
    return _backtest().run_backtest(
        symbol, strategy_id=strategy_id, timeframe=timeframe, bars=bars
    )


@mcp.tool()
def run_walk_forward(
    symbol: str,
    strategy_id: str = "momentum_breakout_crypto",
    timeframe: str = "1h",
    bars: int = 120,
) -> dict[str, Any]:
    """Walk-forward validation (train/validation/OOS). Simulation only."""
    return _backtest().run_walk_forward(
        symbol, strategy_id=strategy_id, timeframe=timeframe, bars=bars
    )


@mcp.tool()
def get_backtest_result(backtest_id: str) -> dict[str, Any]:
    """Fetch a persisted backtest result by id."""
    return _backtest().get_backtest_result(backtest_id)


@mcp.tool()
def get_backtest_report(backtest_id: str) -> dict[str, Any]:
    """Fetch a persisted backtest report by id."""
    return _backtest().get_backtest_report(backtest_id)


@mcp.tool()
def compare_backtests(backtest_ids: list[str]) -> dict[str, Any]:
    """Compare factual metrics across backtests (no profitability claims)."""
    return _backtest().compare_backtests(backtest_ids)


@mcp.tool()
def run_benchmark(symbol: str, timeframe: str = "1h", bars: int = 120) -> dict[str, Any]:
    """Run BUY_AND_HOLD / DCA / SMA baselines for comparison."""
    return _backtest().run_benchmark(symbol, timeframe=timeframe, bars=bars)


@mcp.tool()
def run_prediction_backtest(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Evaluate prediction-market forecasts (Brier/log-loss). Simulation only."""
    return _backtest().run_prediction_backtest(rows)


# --- Phase 8 learning tools (paper / read-only; never place orders) ---
_learning_tools = None


def _learning():
    global _learning_tools
    if _learning_tools is None:
        from crypto_trading_mcp.mcp_tools.learning import LearningToolSurface

        _learning_tools = LearningToolSurface()
    return _learning_tools


@mcp.tool()
def get_learning_status() -> dict[str, Any]:
    """Self-learning engine status (paper mode)."""
    return _learning().get_learning_status()


@mcp.tool()
def get_learning_memory() -> dict[str, Any]:
    """Learning memory records."""
    return _learning().get_learning_memory()


@mcp.tool()
def search_learning_memory(features: dict[str, Any] | None = None) -> dict[str, Any]:
    """Similarity search over learning memory. Does not veto trades."""
    return _learning().search_learning_memory(features)


@mcp.tool()
def get_trade_postmortem(trade_id: str | None = None) -> dict[str, Any]:
    """Fetch trade post-mortem."""
    return _learning().get_trade_postmortem(trade_id)


@mcp.tool()
def get_failure_patterns() -> dict[str, Any]:
    """Aggregated failure patterns from memory."""
    return _learning().get_failure_patterns()


@mcp.tool()
def get_success_patterns() -> dict[str, Any]:
    """Aggregated success patterns from memory."""
    return _learning().get_success_patterns()


@mcp.tool()
def get_calibration() -> dict[str, Any]:
    """Rolling calibration / Brier status."""
    return _learning().get_calibration()


@mcp.tool()
def get_brier_score() -> dict[str, Any]:
    """Rolling Brier score."""
    return _learning().get_brier_score()


@mcp.tool()
def get_model_status() -> dict[str, Any]:
    """Champion / challenger model status."""
    return _learning().get_model_status()


@mcp.tool()
def get_model_versions() -> dict[str, Any]:
    """Model version registry."""
    return _learning().get_model_versions()


@mcp.tool()
def get_learning_proposals() -> dict[str, Any]:
    """Learning proposals and statuses."""
    return _learning().get_learning_proposals()


@mcp.tool()
def get_champion_strategy() -> dict[str, Any]:
    """Current champion model/strategy candidate."""
    return _learning().get_champion_strategy()


@mcp.tool()
def get_challenger_strategy() -> dict[str, Any]:
    """Current challenger model/strategy candidate."""
    return _learning().get_challenger_strategy()


@mcp.tool()
def run_postmortem(record: dict[str, Any]) -> dict[str, Any]:
    """Run post-mortem on a closed paper trade record. Never places orders."""
    return _learning().run_postmortem(record)


@mcp.tool()
def run_reflection() -> dict[str, Any]:
    """Run structured reflection on latest learning record."""
    return _learning().run_reflection()


@mcp.tool()
def run_retraining() -> dict[str, Any]:
    """Train challenger model (optional XGBoost/RF; fallback logistic). Paper only."""
    return _learning().run_retraining()


@mcp.tool()
def run_learning_validation(proposal_id: str | None = None) -> dict[str, Any]:
    """Validate a learning proposal / current champion state."""
    return _learning().run_learning_validation(proposal_id)


@mcp.tool()
def get_learning_audit(limit: int = 100) -> dict[str, Any]:
    """Learning audit trail."""
    return _learning().get_learning_audit(limit)


@mcp.tool()
def rollback_learning_candidate(reason: str = "manual") -> dict[str, Any]:
    """Rollback to champion; never enables live trading."""
    return _learning().rollback_learning_candidate(reason)


if __name__ == "__main__":
    mcp.run(transport="stdio")
