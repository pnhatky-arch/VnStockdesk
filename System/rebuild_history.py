from __future__ import annotations

from src.universe import get_vn100_universe
from src.data import rebuild_short_cache, cache_diagnostics


def main():
    universe = get_vn100_universe()

    print("=" * 80)
    print("VN100 — REBUILD LONG HISTORY")
    print("=" * 80)
    print(f"Universe: {len(universe)}")

    ok = 0
    errors = []

    for i, symbol in enumerate(universe, 1):
        try:
            df = rebuild_short_cache(symbol)
            info = cache_diagnostics(df)

            print(
                f"[{i}/{len(universe)}] {symbol}: "
                f"{info['rows']} rows | "
                f"{info['years']} years | "
                f"{info['start']} -> {info['end']}"
            )

            ok += 1

        except Exception as exc:
            errors.append(
                (symbol, str(exc))
            )

            print(
                f"[{i}/{len(universe)}] "
                f"{symbol}: ERROR {exc}"
            )

    print()
    print("=" * 80)
    print("REBUILD COMPLETE")
    print("=" * 80)
    print(f"OK: {ok}")
    print(f"ERROR: {len(errors)}")


if __name__ == "__main__":
    main()
