from __future__ import annotations

import hashlib
import math
from typing import Sequence


def hash_vector(values: Sequence[float]) -> str:
    payload = ",".join(f"{v:.8f}" for v in values)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def l2_normalize(values: Sequence[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    an = l2_normalize(a)
    bn = l2_normalize(b)
    return sum(x * y for x, y in zip(an, bn))


def embed_features(feature_vector: Sequence[float]) -> list[float]:
    """Deterministic embedding: L2-normalized feature vector (no external model)."""
    return l2_normalize([0.0 if v is None else float(v) for v in feature_vector])
