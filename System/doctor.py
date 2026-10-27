from __future__ import annotations

from src.bootstrap import KEY_STATUS
from src.universe import get_vn100_universe, get_market_listing
from src.data import fetch_history_long
from src.analyzer import analyze_symbol
from tests.test_offline_pipeline import main as offline_test


def main():
    print("=" * 78)
    print("VnStockDesk — DOCTOR")
    print("=" * 78)

    print(
        "[KEY]",
        "LOADED" if KEY_STATUS["loaded"] else "MISSING",
        "|",
        KEY_STATUS["source"] or "Guest",
    )

    # 1) Internal engine test
    offline_test()

    # 2) VN100 universe
    print()
    print("[LIVE] Testing VN100 universe...")

    universe = get_vn100_universe()

    if len(universe) < 80:
        raise RuntimeError(
            f"Universe bất thường: {len(universe)}"
        )

    print(
        f"[PASS] VN100 universe: {len(universe)} symbols"
    )

    market = get_market_listing("ALL")
    counts = market["exchange"].value_counts().to_dict()
    print(f"[PASS] Toàn thị trường: {len(market)} cổ phiếu; {counts}")

    # 3) Live OHLCV test
    errors = []

    for symbol in universe[:5]:
        try:
            # New HISTORY_FULL interface:
            # no years= / retries= arguments.
            df = fetch_history_long(
                symbol=symbol,
            )

            print(
                f"[PASS] OHLCV {symbol}: "
                f"{len(df)} rows; "
                f"start={df.iloc[0]['time']}; "
                f"latest={df.iloc[-1]['time']}"
            )

            result = analyze_symbol(
                symbol,
                df,
            )

            print(
                f"[PASS] Analysis {symbol}: "
                f"{result['final_signal']}"
            )

            print("=" * 78)
            print("[SYSTEM READY]")
            print("=" * 78)
            return

        except Exception as exc:
            errors.append(
                f"{symbol}: {exc}"
            )

    raise RuntimeError(
        "Không fetch được 5 mã đầu.\n"
        + "\n".join(errors)
    )


if __name__ == "__main__":
    main()
