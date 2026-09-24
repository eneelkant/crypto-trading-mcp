# LLM Providers

Provider routing lives in `src/crypto_trading_mcp/llm/` and `config/llm.yaml`.

Defaults use `LLM_PROVIDER=mock` so agents run without paid APIs.

Supported provider keys (via `.env`, never committed):

```text
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GEMINI_API_KEY=
```

Private prompts and chain-of-thought must not appear in dashboard/EventBus payloads
(`sanitize_payload` in `dashboard/events.py`).
