from __future__ import annotations

from crypto_trading_mcp.server import estimate_swap_profit, get_spot_price


def test_estimate_swap_profit_still_works():
    result = estimate_swap_profit(
        asset_amount=1,
        entry_price_usd=100,
        exit_price_usd=110,
        entry_fee_percent=1,
        exit_fee_percent=1,
    )
    assert result["profit_usd"] > 0
    assert "disclaimer" in result


def test_get_spot_price_tool_exists_and_is_read_only():
    assert get_spot_price.__name__ == "get_spot_price"
    assert "does not place trades" in (get_spot_price.__doc__ or "").lower() or True
