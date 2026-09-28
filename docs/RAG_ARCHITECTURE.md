# RAG Architecture

`RAGContextBuilder` produces CONTEXT ONLY bundles.

RAG must never: execute trades, bypass RiskEngine, override exchange validation, fabricate missing data, or become a hidden execution path.

Retrieved text is wrapped as `<UNTRUSTED_EVIDENCE>` and scanned for prompt-injection patterns (kill switch / live enable / submit order instructions).
