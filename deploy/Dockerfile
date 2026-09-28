FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TRADING_MODE=paper \
    LIVE_TRADING_ENABLED=false \
    CLOUD_PAPER_ISOLATED=true

COPY pyproject.toml README.md ./
COPY src ./src
COPY config ./config
COPY strategies ./strategies

RUN pip install --no-cache-dir -e ".[dev]"

EXPOSE 8050
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "from crypto_trading_mcp.live import LiveTradingGate, LiveExecutionPolicy; \
r=LiveTradingGate().evaluate(LiveExecutionPolicy()); \
assert r['approved'] is False; \
assert r['Live Execution']=='DISABLED'"

CMD ["python", "-m", "crypto_trading_mcp.cloud_paper"]
