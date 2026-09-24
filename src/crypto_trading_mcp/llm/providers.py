from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LLMResponse:
    content: str
    provider: str
    model: str
    latency_ms: float = 0.0
    raw: dict[str, Any] | None = None


class LLMError(RuntimeError):
    """Raised when a provider cannot produce a usable response."""


class LLMProvider(ABC):
    name: str

    @abstractmethod
    def complete(
        self,
        *,
        prompt: str,
        model: str,
        system: str | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        raise NotImplementedError

    def available(self) -> bool:
        return True


class MockLLMProvider(LLMProvider):
    """Deterministic fixture provider for tests and offline development."""

    name = "mock"

    def __init__(self, canned: dict[str, Any] | None = None) -> None:
        self._canned = canned or {}

    def complete(
        self,
        *,
        prompt: str,
        model: str,
        system: str | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        key = _infer_agent_key(system or "", prompt)
        payload = self._canned.get(key) or _default_mock_payload(key, prompt)
        return LLMResponse(
            content=json.dumps(payload),
            provider=self.name,
            model=model or "mock-analyst",
            latency_ms=1.0,
            raw={"mock": True},
        )


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self, base_url: str = "http://localhost:11434/v1") -> None:
        self.base_url = base_url.rstrip("/")

    def available(self) -> bool:
        try:
            import httpx

            response = httpx.get(f"{self.base_url}/models", timeout=2.0)
            return response.status_code < 500
        except Exception:
            return False

    def complete(
        self,
        *,
        prompt: str,
        model: str,
        system: str | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        import time

        import httpx

        started = time.perf_counter()
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                },
                timeout=60.0,
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"Ollama unavailable: {exc}") from exc
        return LLMResponse(
            content=content,
            provider=self.name,
            model=model,
            latency_ms=(time.perf_counter() - started) * 1000,
            raw=data if isinstance(data, dict) else None,
        )


class OpenAICompatibleProvider(LLMProvider):
    name = "openai_compatible"

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str,
        provider_name: str = "openai_compatible",
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.name = provider_name

    def available(self) -> bool:
        return bool(self.api_key and self.base_url)

    def complete(
        self,
        *,
        prompt: str,
        model: str,
        system: str | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        if not self.available():
            raise LLMError(f"{self.name} is not configured")
        import time

        import httpx

        started = time.perf_counter()
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                },
                timeout=60.0,
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"{self.name} request failed: {exc}") from exc
        return LLMResponse(
            content=content,
            provider=self.name,
            model=model,
            latency_ms=(time.perf_counter() - started) * 1000,
            raw=data if isinstance(data, dict) else None,
        )


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, api_key: str | None) -> None:
        self.api_key = api_key

    def available(self) -> bool:
        return bool(self.api_key)

    def complete(
        self,
        *,
        prompt: str,
        model: str,
        system: str | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        if not self.available():
            raise LLMError("Anthropic is not configured")
        import time

        import httpx

        started = time.perf_counter()
        headers = {
            "x-api-key": self.api_key or "",
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        body: dict[str, Any] = {
            "model": model,
            "max_tokens": 1024,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            body["system"] = system
        try:
            response = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=body,
                timeout=60.0,
            )
            response.raise_for_status()
            data = response.json()
            content = "".join(
                block.get("text", "")
                for block in data.get("content", [])
                if block.get("type") == "text"
            )
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"Anthropic request failed: {exc}") from exc
        return LLMResponse(
            content=content,
            provider=self.name,
            model=model,
            latency_ms=(time.perf_counter() - started) * 1000,
            raw=data if isinstance(data, dict) else None,
        )


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, api_key: str | None) -> None:
        self.api_key = api_key

    def available(self) -> bool:
        return bool(self.api_key)

    def complete(
        self,
        *,
        prompt: str,
        model: str,
        system: str | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        if not self.available():
            raise LLMError("Gemini is not configured")
        import time

        import httpx

        started = time.perf_counter()
        text = f"{system}\n\n{prompt}" if system else prompt
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent"
        )
        try:
            response = httpx.post(
                url,
                params={"key": self.api_key},
                json={
                    "contents": [{"parts": [{"text": text}]}],
                    "generationConfig": {"temperature": temperature},
                },
                timeout=60.0,
            )
            response.raise_for_status()
            data = response.json()
            content = data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"Gemini request failed: {exc}") from exc
        return LLMResponse(
            content=content,
            provider=self.name,
            model=model,
            latency_ms=(time.perf_counter() - started) * 1000,
            raw=data if isinstance(data, dict) else None,
        )


class LLMRouter:
    """Routes agent completions to configured providers with fail-closed semantics."""

    def __init__(self, providers: dict[str, LLMProvider] | None = None) -> None:
        self._providers = providers or {"mock": MockLLMProvider()}

    @classmethod
    def from_settings(cls, settings: Any) -> LLMRouter:
        providers: dict[str, LLMProvider] = {
            "mock": MockLLMProvider(),
            "ollama": OllamaProvider(
                base_url=settings.openai_api_base or "http://localhost:11434/v1"
            ),
            "openai": OpenAICompatibleProvider(
                api_key=settings.openai_api_key,
                base_url=settings.openai_api_base or "https://api.openai.com/v1",
                provider_name="openai",
            ),
            "openai_compatible": OpenAICompatibleProvider(
                api_key=settings.openai_api_key,
                base_url=settings.openai_api_base or "http://localhost:11434/v1",
            ),
            "anthropic": AnthropicProvider(settings.anthropic_api_key),
            "gemini": GeminiProvider(settings.gemini_api_key),
        }
        return cls(providers)

    def get(self, provider: str) -> LLMProvider:
        if provider not in self._providers:
            raise LLMError(f"Unknown LLM provider: {provider}")
        return self._providers[provider]

    def complete(
        self,
        *,
        provider: str,
        model: str,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.0,
        fallbacks: list[str] | None = None,
    ) -> LLMResponse:
        chain = [provider, *(fallbacks or [])]
        errors: list[str] = []
        for name in chain:
            try:
                client = self.get(name)
                if not client.available():
                    errors.append(f"{name}: unavailable")
                    continue
                return client.complete(
                    prompt=prompt,
                    model=model,
                    system=system,
                    temperature=temperature,
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{name}: {exc}")
        raise LLMError(
            "No usable LLM provider. New discretionary trades must not be opened. "
            + "; ".join(errors)
        )

    def parse_json_content(self, content: str) -> dict[str, Any]:
        content = content.strip()
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
        match = re.search(r"\{.*\}", content, flags=re.DOTALL)
        if match:
            data = json.loads(match.group(0))
            if isinstance(data, dict):
                return data
        raise LLMError("LLM returned malformed JSON")


def _infer_agent_key(system: str, prompt: str) -> str:
    blob = f"{system}\n{prompt}".lower()
    for key in (
        "consensus",
        "bull",
        "bear",
        "strategy",
        "technical",
        "trend",
        "sentiment",
        "on_chain",
        "on-chain",
        "macro",
        "market_intelligence",
        "market intelligence",
    ):
        if key in blob:
            return key.replace(" ", "_").replace("-", "_")
    return "generic"


def _default_mock_payload(key: str, prompt: str) -> dict[str, Any]:
    bullish = "bullish" in prompt.lower() or "rsi" in prompt.lower()
    if key in {"bull"}:
        return {
            "thesis": "Constructive momentum with supportive trend structure.",
            "supporting_evidence": ["Trend alignment positive", "Momentum supportive"],
            "catalysts": ["Continued volume expansion"],
            "technical_confirmation": ["Price above medium SMA"],
            "risks_to_thesis": ["Sudden volatility spike"],
            "confidence": 0.62 if bullish else 0.45,
        }
    if key in {"bear"}:
        return {
            "thesis": "Asymmetric downside if momentum fails.",
            "supporting_evidence": ["Overbought risk", "Macro uncertainty"],
            "downside_catalysts": ["Risk-off liquidity"],
            "technical_weakness": ["Extended move from mean"],
            "risks_to_thesis": ["Strong trend continuation"],
            "confidence": 0.55,
        }
    if key in {"strategy"}:
        return {
            "market_regime": "trending" if bullish else "range",
            "direction": "LONG" if bullish else "NEUTRAL",
            "strategy_type": "trend_follow" if bullish else "wait",
            "entry_conditions": ["Pullback holds support"],
            "exit_conditions": ["Break of support", "Target reached"],
            "invalidation_conditions": ["Regime flip to high-vol chaos"],
            "time_horizon": "swing",
            "confidence": 0.58 if bullish else 0.4,
            "supporting_evidence": ["Technical bias"],
            "contradicting_evidence": ["Incomplete alternative data"],
        }
    if key in {"consensus"}:
        return {
            "decision": "NEUTRAL",
            "confidence": 0.5,
            "supporting_agents": [],
            "disagreement_summary": "Bull and bear remain contested.",
            "missing_information": [],
            "invalidating_conditions": ["Stale market data"],
            "reasoning": "Preserve disagreement; require stronger confluence.",
        }
    if key in {"technical", "technical_analysis"}:
        return {
            "bullish_signals": ["EMA slope up"] if bullish else [],
            "bearish_signals": [] if bullish else ["Soft momentum"],
            "neutral_signals": ["Mixed oscillators"],
            "trend_strength": "moderate",
            "momentum": "positive" if bullish else "flat",
            "volatility": "normal",
            "confidence": 0.6,
            "reasoning": "Interpretation of deterministic indicators only.",
        }
    if key in {"trend"}:
        return {
            "short_term": "up" if bullish else "sideways",
            "medium_term": "up" if bullish else "sideways",
            "long_term": "up",
            "alignment": "partial",
            "regime_change": False,
            "confidence": 0.57,
            "reasoning": "Multi-horizon SMA structure.",
        }
    if key in {"market_intelligence"}:
        return {
            "technical_summary": "Normalized market snapshot interpreted from deterministic inputs.",
            "confidence": 0.7,
        }
    if key in {"sentiment", "on_chain", "macro", "macro_event"}:
        return {
            "status": "UNAVAILABLE",
            "reason": "No live provider configured in this phase.",
            "confidence": 0.0,
        }
    return {"summary": "Mock analysis", "confidence": 0.5}
