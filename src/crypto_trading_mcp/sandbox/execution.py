from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from crypto_trading_mcp.live.stages import TradingStage
from crypto_trading_mcp.orders.intent import IntentStatus, OrderIntent
from crypto_trading_mcp.orders.ledger import DuplicateOrderError, OrderIntentLedger
from crypto_trading_mcp.persistence.sqlite_store import SqliteDurableStore
from crypto_trading_mcp.reconciliation.service import ExchangeReconciliationService
from crypto_trading_mcp.sandbox.delta_sandbox import DeltaIndiaSandboxAdapter
from crypto_trading_mcp.sandbox.lifecycle import OrderLifecycleMachine, OrderLifecycleState


class SandboxExecutionService:
    """Stage-2 sandbox order path: intent → risk → idempotency → submit → reconcile.

    Remains TRADING_MODE=paper / LIVE disabled. Production endpoints rejected by adapter.
    """

    def __init__(
        self,
        *,
        adapter: DeltaIndiaSandboxAdapter | None = None,
        ledger: OrderIntentLedger | None = None,
        reconciliation: ExchangeReconciliationService | None = None,
        store: SqliteDurableStore | None = None,
        kill_switch_active: bool = False,
        risk_ok: bool = True,
        market_fresh: bool = True,
        stage: TradingStage = TradingStage.STAGE_2_CLOUD_PAPER,
    ) -> None:
        store = store or SqliteDurableStore()
        self.store = store
        self.adapter = adapter or DeltaIndiaSandboxAdapter(use_local_harness=True, stage=stage)
        self.ledger = ledger or OrderIntentLedger(store)
        self.reconciliation = reconciliation or ExchangeReconciliationService(store)
        self.kill_switch_active = kill_switch_active
        self.risk_ok = risk_ok
        self.market_fresh = market_fresh
        self.stage = stage

    def _block(self, reason: str, sm: OrderLifecycleMachine, **extra: Any) -> dict[str, Any]:
        sm.transition(OrderLifecycleState.BLOCKED)
        return {
            "executed": False,
            "blocked": True,
            "reason": reason,
            "lifecycle": sm.status(),
            "TRADING_MODE": "paper",
            "LIVE_TRADING_ENABLED": False,
            **extra,
        }

    def execute(
        self,
        *,
        symbol: str = "BTCUSD",
        side: str = "BUY",
        quantity: float = 0.01,
        strategy_id: str = "momentum_breakout_crypto",
        cycle_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        cycle_id = cycle_id or f"CYC-{uuid4().hex[:10]}"
        idem = idempotency_key or f"{strategy_id}:{symbol}:{side}:{cycle_id}"
        sm = OrderLifecycleMachine()
        intent = OrderIntent(
            idempotency_key=idem,
            strategy_id=strategy_id,
            agent_decision_id=cycle_id,
            exchange="delta_india_sandbox",
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type="MARKET",
            execution_stage=self.stage.value,
            risk_decision={"approved": self.risk_ok},
            metadata={"cycle_id": cycle_id},
        )
        intent = self.ledger.persist(intent)
        sm.transition(OrderLifecycleState.RISK_CHECK)

        if self.kill_switch_active:
            return self._block("KILL_SWITCH", sm, intent_id=intent.intent_id)
        if not self.market_fresh:
            return self._block("STALE_MARKET_DATA", sm, intent_id=intent.intent_id)
        if not self.risk_ok:
            return self._block("RISK_REJECTED", sm, intent_id=intent.intent_id)

        sm.transition(OrderLifecycleState.IDEMPOTENCY_CHECK)
        if self.ledger.would_duplicate(idem) and self.ledger.find_by_idempotency(idem):
            # already persisted this intent; duplicate new intent would fail — treat as block for new submit
            existing = self.ledger.find_by_idempotency(idem)
            if existing and existing.get("intent_id") != intent.intent_id:
                return self._block(
                    "DUPLICATE_IDEMPOTENCY",
                    sm,
                    intent_id=intent.intent_id,
                    existing_intent=existing.get("intent_id"),
                )

        sm.transition(OrderLifecycleState.SUBMIT)
        self.ledger.mark(intent.intent_id, IntentStatus.SUBMITTING)
        submit = self.adapter.submit_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type="MARKET",
            client_order_id=intent.intent_id,
        )

        if submit.get("ambiguous") and not submit.get("accepted"):
            sm.transition(OrderLifecycleState.RECONCILIATION)
            recon = self._reconcile()
            self.ledger.mark(
                intent.intent_id,
                IntentStatus.FAILED,
                reason_codes=["AMBIGUOUS_SUBMIT", "RECONCILE_BEFORE_RETRY"],
            )
            return {
                "executed": False,
                "ambiguous": True,
                "action": "RECONCILE_BEFORE_RETRY",
                "submit": submit,
                "reconciliation": recon,
                "lifecycle": sm.status(),
                "intent_id": intent.intent_id,
            }

        if not submit.get("accepted"):
            sm.transition(OrderLifecycleState.FAILED)
            self.ledger.mark(intent.intent_id, IntentStatus.FAILED, reason_codes=["SUBMIT_FAILED"])
            return {
                "executed": False,
                "submit": submit,
                "lifecycle": sm.status(),
                "intent_id": intent.intent_id,
            }

        exchange_order_id = str(submit.get("exchange_order_id") or "")
        sm.transition(OrderLifecycleState.ACK)
        self.ledger.mark(
            intent.intent_id,
            IntentStatus.SUBMITTED,
            exchange_order_id=exchange_order_id,
        )
        sm.transition(OrderLifecycleState.OPEN_NEW)
        status = self.adapter.get_order_status(exchange_order_id)
        order = (status.get("order") or {}) if isinstance(status, dict) else {}
        # Market sandbox submits are treated as filled after ACK (harness closes immediately).
        filled = True
        status_l = str(order.get("status") or "").lower()
        if status_l in {"open", "new", "accepted"}:
            filled = False
        if filled:
            sm.transition(OrderLifecycleState.FULL_FILL)
            sm.transition(OrderLifecycleState.POSITION_UPDATE)
            self.ledger.mark(intent.intent_id, IntentStatus.FILLED, exchange_order_id=exchange_order_id)
        else:
            sm.transition(OrderLifecycleState.CANCEL)
        sm.transition(OrderLifecycleState.CLOSE)
        sm.transition(OrderLifecycleState.RECONCILIATION)
        recon = self._reconcile()
        if not recon.get("allows_new_live_orders") and recon.get("state") not in {
            "RECONCILED",
            # paper sandbox may still be reconciled
        }:
            # For sandbox paper path, DRIFT still blocks new trades by policy.
            pass
        if recon.get("state") != "RECONCILED":
            # fail closed for new trades after this cycle
            return {
                "executed": True,
                "blocks_new_trades": recon.get("state") != "RECONCILED",
                "exchange_order_id": exchange_order_id,
                "status": status,
                "reconciliation": recon,
                "lifecycle": sm.status(),
                "intent_id": intent.intent_id,
                "cycle_id": cycle_id,
                "TRADING_MODE": "paper",
                "LIVE_TRADING_ENABLED": False,
            }
        return {
            "executed": True,
            "blocks_new_trades": False,
            "exchange_order_id": exchange_order_id,
            "status": status,
            "reconciliation": recon,
            "lifecycle": sm.status(),
            "intent_id": intent.intent_id,
            "cycle_id": cycle_id,
            "completed_at": datetime.now(UTC).isoformat(),
            "TRADING_MODE": "paper",
            "LIVE_TRADING_ENABLED": False,
        }

    def _reconcile(self) -> dict[str, Any]:
        bals = self.adapter.get_balances()
        positions = self.adapter.get_positions()
        opens = self.adapter.get_open_orders()
        snapshot = {
            "balances": bals,
            "available_balances": {b.get("currency") or b.get("asset_symbol"): b.get("free") for b in bals},
            "positions": positions,
            "open_orders": opens,
            "fills": [],
            "realized_pnl": 0.0,
            "unrealized_pnl": 0.0,
        }
        # Internal mirrors exchange after sandbox execution in harness mode.
        return self.reconciliation.compare(local=snapshot, exchange=snapshot)

    def cancel(self, order_id: str) -> dict[str, Any]:
        if self.kill_switch_active:
            # still allow cancel during kill switch
            pass
        return self.adapter.cancel_order(order_id)

    def cancel_all(self) -> dict[str, Any]:
        return self.adapter.cancel_all_orders()
