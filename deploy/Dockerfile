FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TRADING_MODE=paper \
    LIVE_TRADING_ENABLED=false \
    CLOUD_PAPER_ISOLATED=true \
    TRADING_STAGE=STAGE_2_CLOUD_PAPER \
    TZ=UTC \
    HEALTH_PORT=8080

COPY pyproject.toml README.md ./
COPY src ./src
COPY config ./config
COPY strategies ./strategies

RUN pip install --no-cache-dir -e .

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health')"

CMD ["python", "-m", "crypto_trading_mcp.cloud_paper"]
