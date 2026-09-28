# Wallet Security

- CEX trading must not require blockchain private keys.
- Forbidden fields: seed, mnemonic, private_key, bip39, wallet_secret.
- `WalletSecurityPolicy.assert_no_wallet_secrets` enforces config hygiene.
- Future on-chain signing uses isolated `IsolatedSigner` outside the hot CEX path.
- Never log or persist wallet secrets.
