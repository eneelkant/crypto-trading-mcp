from __future__ import annotations

import threading
from typing import Any, Callable


class LearningScheduler:
    """Background-friendly scheduler; failures never block trading."""

    def __init__(self) -> None:
        self._jobs: list[threading.Thread] = []

    def submit(self, fn: Callable[[], Any], name: str = "learning-job") -> None:
        def _wrap() -> None:
            try:
                fn()
            except Exception:
                return

        t = threading.Thread(target=_wrap, name=name, daemon=True)
        self._jobs.append(t)
        t.start()
