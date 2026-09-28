from __future__ import annotations

from typing import Any, Protocol


FORBIDDEN_WALLET_FIELDS = (
    "seed",
    "mnemonic",
    "private_key",
    "privkey",
    "wallet_secret",
    "bip39",
)


class IsolatedSigner(Protocol):
    """Future on-chain signer boundary. Must never live in the trading hot path for CEX."""

    def sign(self, payload: bytes) -> bytes: ...


class WalletSecurityPolicy:
    def assert_no_wallet_secrets(self, mapping: dict[str, Any]) -> None:
        for key in mapping:
            lk = str(key).lower()
            if any(f in lk for f in FORBIDDEN_WALLET_FIELDS):
                raise PermissionError(
                    f"Blockchain wallet secret field forbidden in trading config: {key}"
                )

    def cex_path_allowed_without_wallet(self) -> bool:
        return True
