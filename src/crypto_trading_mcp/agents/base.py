from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from crypto_trading_mcp.agents.messages import AgentMessage, MessageStatus
from crypto_trading_mcp.llm import LLMError
from crypto_trading_mcp.orchestration.context import ExecutionContext


class BaseAgent(ABC):
    """Common agent contract used by the registry and orchestrator."""

    agent_id: ClassVar[str]
    name: ClassVar[str]
    version: ClassVar[str] = "1.0.0"
    responsibility: ClassVar[str] = ""
    config_key: ClassVar[str] = ""

    async def run(self, context: ExecutionContext) -> AgentMessage:
        context.require_no_execution()
        started = time.perf_counter()
        model_cfg = context.settings.agent_model_config(
            self.config_key or self.agent_id
        )
        try:
            payload = await self.analyze(context)
            status = MessageStatus.OK
            if isinstance(payload, dict) and str(payload.get("status", "")).upper() == "UNAVAILABLE":
                status = MessageStatus.UNAVAILABLE
            message = AgentMessage(
                agent=self.name,
                agent_id=self.agent_id,
                symbol=context.symbol,
                decision=payload.get("decision") if isinstance(payload, dict) else None,
                confidence=float(
                    (payload or {}).get("confidence", 0.0)
                    if isinstance(payload, dict)
                    else 0.0
                ),
                evidence=list((payload or {}).get("evidence", []))
                if isinstance(payload, dict)
                else [],
                risk_flags=list((payload or {}).get("risk_flags", []))
                if isinstance(payload, dict)
                else [],
                model=model_cfg["model"],
                provider=model_cfg["provider"],
                version=self.version,
                latency_ms=(time.perf_counter() - started) * 1000,
                status=status,
                payload=payload if isinstance(payload, dict) else {"value": payload},
            )
        except LLMError as exc:
            message = AgentMessage(
                agent=self.name,
                agent_id=self.agent_id,
                symbol=context.symbol,
                decision="NO_TRADE",
                confidence=0.0,
                risk_flags=["llm_unavailable"],
                model=model_cfg["model"],
                provider=model_cfg["provider"],
                version=self.version,
                latency_ms=(time.perf_counter() - started) * 1000,
                status=MessageStatus.ERROR,
                payload={"status": "UNAVAILABLE"},
                error=str(exc),
            )
        except Exception as exc:  # noqa: BLE001
            message = AgentMessage(
                agent=self.name,
                agent_id=self.agent_id,
                symbol=context.symbol,
                decision="NO_TRADE",
                confidence=0.0,
                risk_flags=["agent_error"],
                model=model_cfg["model"],
                provider=model_cfg["provider"],
                version=self.version,
                latency_ms=(time.perf_counter() - started) * 1000,
                status=MessageStatus.ERROR,
                payload={},
                error=str(exc),
            )
        context.store(self.agent_id, message)
        return message

    @abstractmethod
    async def analyze(self, context: ExecutionContext) -> dict[str, Any]:
        raise NotImplementedError

    def llm_json(
        self,
        context: ExecutionContext,
        *,
        system: str,
        prompt: str,
    ) -> dict[str, Any]:
        if context.llm_router is None:
            raise LLMError("LLM router is not configured")
        cfg = context.settings.agent_model_config(self.config_key or self.agent_id)
        response = context.llm_router.complete(
            provider=cfg["provider"],
            model=cfg["model"],
            system=system,
            prompt=prompt,
        )
        return context.llm_router.parse_json_content(response.content)
