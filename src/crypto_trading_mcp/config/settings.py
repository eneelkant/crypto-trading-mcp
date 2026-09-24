from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

TradingMode = Literal["backtest", "paper", "coinbase_readonly", "live"]

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = REPO_ROOT / "config"


def _load_yaml(name: str) -> dict[str, Any]:
    path = CONFIG_DIR / name
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config {name} must be a mapping")
    return data


class Settings(BaseSettings):
    """Runtime settings. Live trading stays disabled unless explicitly enabled later."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    trading_mode: TradingMode = "paper"
    live_trading_enabled: bool = False

    llm_provider: str = "mock"
    model_name: str = "mock-analyst"
    openai_api_base: str | None = None
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    gemini_api_key: str | None = None

    default_exchange_id: str = "kraken"
    market_data_max_age_seconds: int = 120

    def assert_no_live_trading(self) -> None:
        if self.trading_mode == "live" and self.live_trading_enabled:
            raise RuntimeError(
                "Live trading is not implemented in this phase and must remain disabled."
            )

    @property
    def real_money_enabled(self) -> bool:
        return self.trading_mode == "live" and self.live_trading_enabled

    def trading_yaml(self) -> dict[str, Any]:
        return _load_yaml("trading.yaml")

    def llm_yaml(self) -> dict[str, Any]:
        return _load_yaml("llm.yaml")

    def agent_model_config(self, agent_key: str) -> dict[str, str]:
        agents = self.llm_yaml().get("agents", {})
        entry = agents.get(agent_key, {}) if isinstance(agents, dict) else {}
        provider = str(entry.get("provider") or self.llm_provider)
        model = str(entry.get("model") or self.model_name)
        return {"provider": provider, "model": model}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    # YAML defaults can reinforce env without overriding explicit env when already set.
    trading = settings.trading_yaml()
    if "trading_mode" in trading and "TRADING_MODE" not in __import__("os").environ:
        object.__setattr__(settings, "trading_mode", trading["trading_mode"])
    if (
        "live_trading_enabled" in trading
        and "LIVE_TRADING_ENABLED" not in __import__("os").environ
    ):
        object.__setattr__(
            settings, "live_trading_enabled", bool(trading["live_trading_enabled"])
        )
    return settings
