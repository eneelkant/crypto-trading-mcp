"""Cloud-paper entrypoint. Incapable of submitting live/production orders."""

from __future__ import annotations

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from crypto_trading_mcp.config.settings import get_settings
from crypto_trading_mcp.live.gate import LiveTradingGate
from crypto_trading_mcp.live.policy import LiveExecutionPolicy
from crypto_trading_mcp.live.stages import TradingStage
from crypto_trading_mcp.sandbox.stage2_runtime import Stage2CloudPaperRuntime


def assert_cloud_paper_isolation() -> None:
    settings = get_settings()
    if settings.trading_mode != "paper" or settings.live_trading_enabled:
        raise RuntimeError("Cloud-paper requires TRADING_MODE=paper and LIVE_TRADING_ENABLED=false")
    if os.getenv("LIVE_TRADING_ENABLED", "false").lower() in {"1", "true", "yes"}:
        raise RuntimeError("Cloud-paper refuses LIVE_TRADING_ENABLED=true")
    gate = LiveTradingGate()
    result = gate.evaluate(
        LiveExecutionPolicy(
            trading_mode="paper",
            live_trading_enabled=False,
            stage=TradingStage.STAGE_2_CLOUD_PAPER,
            cloud_paper_isolated=True,
            credentials_healthy=True,
            credentials_allow_trading=True,
            market_data_fresh=True,
            exchange_healthy=True,
            reconciliation_ok=True,
            order_valid=True,
            exchange="coinbase",
            exchange_allowlist=["coinbase"],
        )
    )
    if result["approved"]:
        raise RuntimeError("Cloud-paper isolation failed: live gate approved")


def _make_handler(runtime: Stage2CloudPaperRuntime):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, code: int, payload: dict) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health":
                self._json(200, runtime.health())
            elif self.path == "/ready":
                ready = runtime.readiness()
                self._json(200 if ready.get("ready") else 503, ready)
            elif self.path == "/livez":
                self._json(200, runtime.liveness())
            else:
                self._json(404, {"error": "not_found"})

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

    return Handler


def main() -> None:
    assert_cloud_paper_isolation()
    runtime = Stage2CloudPaperRuntime(use_local_harness=True)
    runtime.start()

    port = int(os.getenv("HEALTH_PORT", "8080"))
    server = HTTPServer(("0.0.0.0", port), _make_handler(runtime))
    thread = threading.Thread(target=server.serve_forever, name="health", daemon=True)
    thread.start()

    print(
        json.dumps(
            {
                "mode": "cloud_paper",
                "stage": TradingStage.STAGE_2_CLOUD_PAPER.value,
                "TRADING_MODE": "paper",
                "LIVE_TRADING_ENABLED": False,
                "Live Execution": "DISABLED",
                "health_port": port,
            }
        )
    )

    max_cycles = int(os.getenv("PAPER_MAX_CYCLES", "0") or 0)
    interval = float(os.getenv("PAPER_LOOP_INTERVAL", "30"))
    completed = 0
    try:
        while True:
            runtime.run_cycle()
            completed += 1
            if max_cycles and completed >= max_cycles:
                break
            time.sleep(interval)
    finally:
        runtime.shutdown()
        server.shutdown()


if __name__ == "__main__":
    main()
