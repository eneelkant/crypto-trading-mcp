from __future__ import annotations


class LiveExecutionBlocked(RuntimeError):
    """Raised when code attempts authenticated/live exchange execution."""


class PaperExchangeError(RuntimeError):
    pass


class InsufficientCashError(PaperExchangeError):
    pass


class InvalidOrderError(PaperExchangeError):
    pass


class ExchangeUnavailableError(PaperExchangeError):
    pass


class StaleMarketDataError(PaperExchangeError):
    pass


class RiskRejectedError(PaperExchangeError):
    pass


class KillSwitchActiveError(PaperExchangeError):
    pass
