from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from crypto_trading_mcp.backtest.models import BacktestResult
from crypto_trading_mcp.config.settings import REPO_ROOT


FORBIDDEN_CLAIMS = (
    "best strategy",
    "guaranteed profitable",
    "will make money",
    "safe strategy",
)


def _assert_no_hype(text: str) -> None:
    lower = text.lower()
    for phrase in FORBIDDEN_CLAIMS:
        if phrase in lower:
            raise ValueError(f"Report contains forbidden profitability claim: {phrase}")


def write_json_report(result: BacktestResult, path: Path | None = None) -> Path:
    reports = REPO_ROOT / "reports" / "backtests"
    reports.mkdir(parents=True, exist_ok=True)
    path = path or (reports / f"{result.identity.backtest_id}.json")
    payload = result.to_dict()
    _assert_no_hype(json.dumps(payload))
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


def write_markdown_report(result: BacktestResult, path: Path | None = None) -> Path:
    reports = REPO_ROOT / "reports" / "backtests"
    reports.mkdir(parents=True, exist_ok=True)
    path = path or (reports / f"{result.identity.backtest_id}.md")
    m = result.metrics
    lines = [
        f"# Backtest Report: {result.identity.backtest_id}",
        "",
        f"- Strategy: `{result.identity.strategy_id}` @ `{result.identity.strategy_version}`",
        f"- Config hash: `{result.identity.strategy_config_hash}`",
        f"- Instrument: `{result.identity.instrument}` / `{result.identity.timeframe}`",
        f"- Data: `{result.identity.data_source}` `{result.identity.data_version}`",
        f"- Range: `{result.identity.date_start}` → `{result.identity.date_end}`",
        f"- Partition: `{result.identity.partition.value}`",
        f"- Initial capital: {result.initial_capital}",
        f"- Final equity: {result.final_equity}",
        f"- Net return: {m.get('return_pct')}%",
        f"- Gross P&L: {m.get('gross_pnl')}",
        f"- Fees: {m.get('fees')}",
        f"- Slippage: {m.get('slippage')}",
        f"- Net P&L: {m.get('net_pnl')}",
        f"- Max drawdown: {m.get('max_drawdown')}",
        f"- Sharpe: {m.get('sharpe_ratio')}",
        f"- Sortino: {m.get('sortino_ratio')}",
        f"- Profit factor: {m.get('profit_factor')}",
        f"- Win rate: {m.get('win_rate')}",
        f"- Trade count: {m.get('trade_count')}",
        f"- Turnover: {m.get('turnover')}",
        f"- Risk rejections: {result.risk_rejections}",
        "",
        "TRADING_MODE: PAPER",
        "REAL_MONEY: DISABLED",
        "",
        result.disclaimer,
    ]
    text = "\n".join(lines)
    _assert_no_hype(text)
    path.write_text(text, encoding="utf-8")
    return path


def write_csv_trades(result: BacktestResult, path: Path | None = None) -> Path:
    reports = REPO_ROOT / "reports" / "backtests"
    reports.mkdir(parents=True, exist_ok=True)
    path = path or (reports / f"{result.identity.backtest_id}_trades.csv")
    rows = result.trades
    if not rows:
        path.write_text("trade_id\n", encoding="utf-8")
        return path
    fields = sorted({k for row in rows for k in row.keys()})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_equity_csv(result: BacktestResult, path: Path | None = None) -> Path:
    reports = REPO_ROOT / "reports" / "backtests"
    reports.mkdir(parents=True, exist_ok=True)
    path = path or (reports / f"{result.identity.backtest_id}_equity.csv")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["timestamp", "equity", "cash", "drawdown", "daily_pnl"]
        )
        writer.writeheader()
        for pt in result.equity_curve:
            writer.writerow(pt.model_dump())
    return path


def summarize_result(result: BacktestResult) -> dict[str, Any]:
    return {
        "backtest_id": result.identity.backtest_id,
        "strategy": result.identity.strategy_id,
        "version": result.identity.strategy_version,
        "config_hash": result.identity.strategy_config_hash,
        "instrument": result.identity.instrument,
        "timeframe": result.identity.timeframe,
        "data_range": [result.identity.date_start, result.identity.date_end],
        "data_source": result.identity.data_source,
        "partition": result.identity.partition.value,
        "initial_capital": result.initial_capital,
        "final_equity": result.final_equity,
        "return_pct": result.metrics.get("return_pct"),
        "drawdown": result.metrics.get("max_drawdown"),
        "sharpe": result.metrics.get("sharpe_ratio"),
        "sortino": result.metrics.get("sortino_ratio"),
        "profit_factor": result.metrics.get("profit_factor"),
        "win_rate": result.metrics.get("win_rate"),
        "trade_count": result.metrics.get("trade_count"),
        "fees": result.metrics.get("fees"),
        "slippage": result.metrics.get("slippage"),
        "turnover": result.metrics.get("turnover"),
        "risk_rejections": result.risk_rejections,
        "structural_hash": result.structural_hash,
        "TRADING_MODE": "PAPER",
        "REAL_MONEY": "DISABLED",
        "disclaimer": result.disclaimer,
    }
