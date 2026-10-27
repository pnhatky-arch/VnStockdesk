from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re


def _clean_name(name: str) -> str:
    value = " ".join(str(name or "").strip().split())
    if not 1 <= len(value) <= 80:
        raise ValueError("Tên danh mục phải có từ 1 đến 80 ký tự.")
    if not re.fullmatch(r"[\wÀ-ỹ .()&+\-]+", value, flags=re.UNICODE):
        raise ValueError("Tên danh mục chứa ký tự không hợp lệ.")
    return value


class PortfolioStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> dict:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return {}

    def _write(self, payload: dict) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def list(self) -> list[dict]:
        rows = []
        for name, item in self._read().items():
            if isinstance(item, dict):
                rows.append({"name": name, **item})
        return sorted(rows, key=lambda item: str(item.get("updated_at", "")), reverse=True)

    def get(self, name: str) -> dict:
        clean = _clean_name(name)
        item = self._read().get(clean)
        if not isinstance(item, dict):
            raise KeyError(f"Không tìm thấy danh mục {clean}.")
        return {"name": clean, **item}

    def save(self, name: str, basket: str, positions: list[dict]) -> dict:
        clean = _clean_name(name)
        normalized = []
        for row in positions:
            symbol = str(row.get("symbol") or "").upper().strip()
            quantity = int(float(row.get("quantity") or 0))
            buy_price = float(row.get("buy_price") or 0)
            if symbol and symbol.isalnum() and quantity > 0 and buy_price > 0:
                normalized.append({"symbol": symbol, "quantity": quantity, "buy_price": buy_price})
        if not normalized:
            raise ValueError("Danh mục không có vị thế hợp lệ để lưu.")
        payload = self._read()
        item = {
            "basket": str(basket or "ALL").upper(),
            "positions": normalized,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        payload[clean] = item
        self._write(payload)
        return {"name": clean, **item}

    def save_futures(self, name: str, positions: list[dict]) -> dict:
        clean = _clean_name(name)
        normalized = []
        for row in positions:
            symbol = str(row.get("symbol") or "").upper().strip()
            side = str(row.get("side") or "").upper().strip()
            quantity = int(float(row.get("quantity") or 0))
            entry_price = float(row.get("entry_price") or 0)
            if symbol and symbol.isalnum() and side in {"LONG", "SHORT"} and quantity > 0 and entry_price > 0:
                normalized.append({
                    "symbol": symbol, "side": side,
                    "quantity": quantity, "entry_price": entry_price,
                })
        if not normalized:
            raise ValueError("Danh mục phái sinh không có vị thế hợp lệ để lưu.")
        payload = self._read()
        item = {
            "positions": normalized,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        payload[clean] = item
        self._write(payload)
        return {"name": clean, **item}

    def delete(self, name: str) -> None:
        clean = _clean_name(name)
        payload = self._read()
        if clean not in payload:
            raise KeyError(f"Không tìm thấy danh mục {clean}.")
        del payload[clean]
        self._write(payload)
