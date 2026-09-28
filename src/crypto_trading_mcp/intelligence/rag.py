from __future__ import annotations

import hashlib
import re
from typing import Any

from crypto_trading_mcp.intelligence.sources import IntelligenceRecord, SourceCategory


_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"disregard\s+(all\s+)?safety",
    r"override\s+risk",
    r"disable\s+kill\s*switch",
    r"set\s+LIVE_TRADING_ENABLED\s*=\s*true",
    r"submit\s+order",
    r"exfiltrate",
    r"reveal\s+(api|secret|password)",
]


class PromptInjectionError(ValueError):
    pass


class RAGContextBuilder:
    """Builds untrusted context bundles for agents. Never an execution path."""

    def __init__(self, *, max_docs: int = 8) -> None:
        self.max_docs = max_docs
        self._seen_hashes: set[str] = set()

    def _hash(self, record: IntelligenceRecord) -> str:
        raw = f"{record.source_type}:{record.provenance}:{record.content}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def sanitize_text(self, text: str) -> str:
        cleaned = text
        for pattern in _INJECTION_PATTERNS:
            cleaned = re.sub(pattern, "[BLOCKED_INSTRUCTION]", cleaned, flags=re.IGNORECASE)
        # Containment: wrap as quoted evidence
        return f"<UNTRUSTED_EVIDENCE>{cleaned}</UNTRUSTED_EVIDENCE>"

    def detect_injection(self, text: str) -> bool:
        return any(re.search(p, text, flags=re.IGNORECASE) for p in _INJECTION_PATTERNS)

    def build(self, records: list[IntelligenceRecord]) -> dict[str, Any]:
        docs: list[dict[str, Any]] = []
        blocked = 0
        for rec in records:
            if rec.status != "AVAILABLE":
                continue
            h = self._hash(rec)
            if h in self._seen_hashes:
                continue
            self._seen_hashes.add(h)
            content = rec.content
            text = content if isinstance(content, str) else str(content)
            if self.detect_injection(text):
                blocked += 1
                text = self.sanitize_text(text)
            else:
                text = self.sanitize_text(text)
            docs.append(
                {
                    **rec.to_context_dict(),
                    "content": text,
                    "trusted": False,
                    "can_execute_trades": False,
                    "can_override_risk": False,
                }
            )
            if len(docs) >= self.max_docs:
                break
        return {
            "documents": docs,
            "blocked_injection_attempts": blocked,
            "source_categories": sorted({d["source_type"] for d in docs}),
            "role": "CONTEXT_ONLY",
            "execution_forbidden": True,
            "risk_override_forbidden": True,
        }

    def assert_not_executable(self, bundle: dict[str, Any]) -> None:
        if not bundle.get("execution_forbidden"):
            raise RuntimeError("RAG bundle must mark execution_forbidden")
        if bundle.get("can_execute_trades"):
            raise RuntimeError("RAG must never execute trades")
