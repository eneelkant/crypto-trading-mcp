from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any, Protocol


class AlertSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class AlertChannel(Protocol):
    name: str

    def send(self, alert: dict[str, Any]) -> dict[str, Any]: ...


class InMemoryAlertChannel:
    name = "memory"

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    def send(self, alert: dict[str, Any]) -> dict[str, Any]:
        self.sent.append(alert)
        return {"ok": True, "channel": self.name}


class SlackAlertChannel:
    name = "slack"

    def __init__(self, webhook_url: str | None = None) -> None:
        self.webhook_url = webhook_url

    def send(self, alert: dict[str, Any]) -> dict[str, Any]:
        if not self.webhook_url:
            return {"ok": False, "channel": self.name, "reason": "not_configured"}
        return {"ok": True, "channel": self.name, "queued": True, "alert_type": alert.get("type")}


class EmailAlertChannel:
    name = "email"

    def __init__(self, to_addr: str | None = None) -> None:
        self.to_addr = to_addr

    def send(self, alert: dict[str, Any]) -> dict[str, Any]:
        if not self.to_addr:
            return {"ok": False, "channel": self.name, "reason": "not_configured"}
        return {"ok": True, "channel": self.name, "queued": True}


class PagerDutyAlertChannel:
    name = "pagerduty"

    def __init__(self, routing_key: str | None = None) -> None:
        self.routing_key = routing_key

    def send(self, alert: dict[str, Any]) -> dict[str, Any]:
        if not self.routing_key:
            return {"ok": False, "channel": self.name, "reason": "not_configured"}
        return {"ok": True, "channel": self.name, "queued": True}


class CloudMonitoringAlertChannel:
    name = "cloud_monitoring"

    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled

    def send(self, alert: dict[str, Any]) -> dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "channel": self.name, "reason": "not_configured"}
        return {"ok": True, "channel": self.name, "queued": True}


class AlertManager:
    """Fan-out alerts. Never include credentials in payloads."""

    def __init__(self, channels: list[AlertChannel] | None = None) -> None:
        self.channels = channels or [InMemoryAlertChannel()]
        self.history: list[dict[str, Any]] = []

    def emit(
        self,
        alert_type: str,
        *,
        severity: AlertSeverity = AlertSeverity.WARNING,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        from crypto_trading_mcp.credentials.redaction import redact_payload

        alert = {
            "type": alert_type,
            "severity": severity.value,
            "timestamp": datetime.now(UTC).isoformat(),
            "details": redact_payload(details or {}),
            "LIVE_TRADING_ENABLED": False,
        }
        self.history.append(alert)
        results = [ch.send(alert) for ch in self.channels]
        return {"alert": alert, "results": results}
