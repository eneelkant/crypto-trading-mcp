from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, computed_field

from crypto_trading_mcp.exchange.models import AssetClass, InstrumentMeta, Order, OrderSide, OrderType, SettlementType
from crypto_trading_mcp.exchange.paper import PaperExchange
from crypto_trading_mcp.exchange.settlement import (
    build_settlement_record,
    prediction_settlement_value,
)


class PredictionContract(BaseModel):
    """Paper prediction-market contract (Polymarket/Kalshi-style simulation only)."""

    market_id: str
    question: str
    outcome: str  # YES or NO
    price: float = Field(ge=0.0, le=1.0)
    probability: float = Field(ge=0.0, le=1.0)
    resolution_time: datetime | None = None
    liquidity: float = 0.0
    resolved: bool = False
    winning_outcome: str | None = None  # from simulation dataset only

    @computed_field  # type: ignore[prop-decorator]
    @property
    def symbol(self) -> str:
        return f"PREDICT/{self.market_id}/{self.outcome.upper()}"


class EnsembleAttribution(BaseModel):
    grok_weight: float = 0.0
    claude_weight: float = 0.0
    gpt_weight: float = 0.0
    gemini_weight: float = 0.0
    deepseek_weight: float = 0.0
    individual_predictions: dict[str, float] = Field(default_factory=dict)
    ensemble_probability: float = 0.0
    market_probability: float = 0.0
    edge: float = 0.0
    brier_history: list[float] = Field(default_factory=list)


class PredictionMarketBook:
    """Deterministic prediction-contract book on top of PaperExchange.

    Settlement model (documented):
    - Contracts priced in [0, 1] as probability dollars.
    - BUY YES at price p costs p per contract; settles to 1 if YES wins else 0.
    - BUY NO at price q costs q; settles to 1 if NO wins else 0.
    - Matching assumption for limits: same as paper limit rules on probability price.
    - Outcomes come only from the simulation dataset (`winning_outcome`), never invented.
    """

    def __init__(self, exchange: PaperExchange) -> None:
        self.exchange = exchange
        self.markets: dict[str, PredictionContract] = {}
        self.attributions: dict[str, EnsembleAttribution] = {}
        self.settlements: list[dict[str, Any]] = []

    def list_markets(self) -> list[dict[str, Any]]:
        return [m.model_dump(mode="json") for m in self.markets.values()]

    def register_market(self, contract: PredictionContract) -> PredictionContract:
        self.markets[contract.symbol] = contract
        self.exchange.set_price(contract.symbol, contract.price)
        self.exchange.instruments[contract.symbol] = self.exchange.instruments.get(
            contract.symbol
        ) or InstrumentMeta(
            symbol=contract.symbol,
            asset_class=AssetClass.PREDICTION_CONTRACT,
            tick_size=0.01,
            lot_size=1.0,
            settlement_type=SettlementType.BINARY,
        )
        return contract

    def buy(
        self,
        symbol: str,
        quantity: float,
        *,
        side: OrderSide,
        strategy_id: str | None = None,
        attribution: EnsembleAttribution | None = None,
        model_probability: float | None = None,
    ) -> Order:
        contract = self.markets[symbol]
        market_p = contract.probability
        model_p = float(model_probability if model_probability is not None else market_p)
        edge = model_p - market_p
        order = Order(
            symbol=symbol,
            instrument_type=AssetClass.PREDICTION_CONTRACT,
            side=side,
            order_type=OrderType.MARKET,
            quantity=quantity,
            strategy_id=strategy_id,
            metadata={
                "market_probability": market_p,
                "model_probability": model_p,
                "edge": edge,
            },
        )
        if attribution:
            self.attributions[order.order_id or "pending"] = attribution
            order.metadata["ensemble"] = attribution.model_dump()
        filled = self.exchange.create_order(order, market_price=contract.price)
        if attribution and filled.order_id:
            self.attributions[filled.order_id] = attribution
        return filled

    def resolve(self, market_id: str, winning_outcome: str) -> list[dict[str, Any]]:
        """Settle all open paper positions for this market using dataset outcome."""
        winning = winning_outcome.upper()
        results: list[dict[str, Any]] = []
        for symbol, contract in list(self.markets.items()):
            if contract.market_id != market_id:
                continue
            contract.resolved = True
            contract.winning_outcome = winning
            if symbol not in self.exchange.portfolio.positions:
                continue
            settlement = prediction_settlement_value(
                held_outcome=contract.outcome, winning_outcome=winning
            )
            pnl = self.exchange.portfolio.close_position(symbol, price=settlement, fee=0.0)
            record = build_settlement_record(
                market_id=market_id,
                symbol=symbol,
                winning_outcome=winning,
                settlement_value=settlement,
                pnl=pnl,
            ).to_dict()
            self.settlements.append(record)
            results.append(record)
        return results


def brier_score(probability: float, outcome: int) -> float:
    """outcome is 1 if event occurred else 0."""
    return (probability - outcome) ** 2
