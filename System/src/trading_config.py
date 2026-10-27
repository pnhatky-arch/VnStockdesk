from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class TradingConfig:
    initial_cash_vnd: float = float(os.getenv("VN_TRADING_INITIAL_CASH", "1000000000"))
    risk_per_trade: float = float(os.getenv("VN_TRADING_RISK_PER_TRADE", "0.01"))
    max_position_pct: float = float(os.getenv("VN_TRADING_MAX_POSITION_PCT", "0.20"))
    # Legacy compatibility only; the engine/broker never enforce a count cap.
    # Cash, allocation and daily-loss limits still apply.
    max_positions: int = 0
    max_daily_loss_pct: float = float(os.getenv("VN_TRADING_MAX_DAILY_LOSS_PCT", "0.03"))
    lot_size: int = int(os.getenv("VN_TRADING_LOT_SIZE", "100"))
    price_multiplier: int = int(os.getenv("VN_TRADING_PRICE_MULTIPLIER", "1000"))
    buy_fee_rate: float = float(os.getenv("VN_TRADING_BUY_FEE_RATE", "0.0015"))
    sell_fee_rate: float = float(os.getenv("VN_TRADING_SELL_FEE_RATE", "0.0015"))
    sell_tax_rate: float = float(os.getenv("VN_TRADING_SELL_TAX_RATE", "0.001"))


DEFAULT_CONFIG = TradingConfig()
