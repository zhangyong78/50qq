from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

OPTION_MULTIPLIER = 10000
VALID_MODES = frozenset({"mode1", "mode2", "mode3", "mode4"})


def _number(record: dict[str, Any], key: str, default: float | None = None) -> float:
    value = record.get(key, default)
    if value is None:
        raise ValueError(f"Missing required value: {key}")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid numeric value: {key}") from exc
    if not math.isfinite(result):
        raise ValueError(f"Invalid numeric value: {key}")
    return result


def validate_settlement_record(record: dict[str, Any]) -> None:
    mode = str(record.get("mode", ""))
    if mode not in VALID_MODES:
        raise ValueError("Unsupported strategy mode")

    shares = _number(record, "stock_shares")
    contracts = _number(record, "option_contracts")
    if shares <= 0 or contracts <= 0:
        raise ValueError("Stock shares and option contracts must be positive")
    if shares != contracts * OPTION_MULTIPLIER:
        raise ValueError("Stock shares must equal option contracts multiplied by 10000")

    for key in ("strike", "stock_price", "option_premium"):
        if _number(record, key) < 0:
            raise ValueError(f"{key} cannot be negative")


def calculate_settled_profit(record: dict[str, Any]) -> float:
    validate_settlement_record(record)
    mode = str(record["mode"])
    shares = _number(record, "stock_shares")
    contracts = _number(record, "option_contracts")
    strike = _number(record, "strike")
    stock_price = _number(record, "stock_price")
    option_premium = _number(record, "option_premium")
    commission = _number(record, "stock_commission_rate", 0.0002)
    buy_open_fee = _number(record, "option_buy_open_fee", 2.0)
    active_exercise_fee = _number(record, "active_exercise_fee", 4.0)
    borrow_cost = _number(record, "borrow_cost", 0.0)

    if mode == "mode1":
        profit = strike * shares - (
            stock_price * shares * (1 + commission)
            + option_premium * contracts
            + buy_open_fee * contracts
            + active_exercise_fee * contracts
        )
    elif mode == "mode2":
        profit = stock_price * shares * (1 - commission) + option_premium * contracts - strike * shares
    elif mode == "mode3":
        profit = strike * shares + option_premium * contracts - stock_price * shares * (1 + commission)
    else:
        profit = stock_price * shares * (1 - commission) - (
            strike * shares
            + option_premium * contracts
            + buy_open_fee * contracts
            + active_exercise_fee * contracts
            + borrow_cost
        )

    return round(profit, 2)


def format_settlement_formula(record: dict[str, Any]) -> str:
    validate_settlement_record(record)
    mode = str(record["mode"])
    shares = _number(record, "stock_shares")
    contracts = _number(record, "option_contracts")
    strike = _number(record, "strike")
    stock_price = _number(record, "stock_price")
    option_premium = _number(record, "option_premium")
    commission = _number(record, "stock_commission_rate", 0.0002)
    buy_open_fee = _number(record, "option_buy_open_fee", 2.0)
    active_exercise_fee = _number(record, "active_exercise_fee", 4.0)
    borrow_cost = _number(record, "borrow_cost", 0.0)
    result = calculate_settled_profit(record)

    if mode == "mode1":
        expression = (
            f"{strike:.4f}*{shares:.0f} - "
            f"[{stock_price:.4f}*{shares:.0f}*(1+{commission:.6f}) + "
            f"{option_premium:.2f}*{contracts:.0f} + {buy_open_fee:.2f}*{contracts:.0f} + "
            f"{active_exercise_fee:.2f}*{contracts:.0f}]"
        )
    elif mode == "mode2":
        expression = (
            f"{stock_price:.4f}*{shares:.0f}*(1-{commission:.6f}) + "
            f"{option_premium:.2f}*{contracts:.0f} - {strike:.4f}*{shares:.0f}"
        )
    elif mode == "mode3":
        expression = (
            f"{strike:.4f}*{shares:.0f} + {option_premium:.2f}*{contracts:.0f} - "
            f"{stock_price:.4f}*{shares:.0f}*(1+{commission:.6f})"
        )
    else:
        expression = (
            f"{stock_price:.4f}*{shares:.0f}*(1-{commission:.6f}) - "
            f"[{strike:.4f}*{shares:.0f} + {option_premium:.2f}*{contracts:.0f} + "
            f"{buy_open_fee:.2f}*{contracts:.0f} + {active_exercise_fee:.2f}*{contracts:.0f} + "
            f"{borrow_cost:.2f}]"
        )

    return f"{expression} = {result:.2f}"


class StrategyLedgerStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)

    def _path_for_month(self, month_text: str) -> Path:
        if len(month_text) != 7 or month_text[4] != "-":
            raise ValueError("Month format must be YYYY-MM")
        try:
            year = int(month_text[:4])
            month = int(month_text[5:])
        except ValueError as exc:
            raise ValueError("Month format must be YYYY-MM") from exc
        if year < 2000 or not 1 <= month <= 12:
            raise ValueError("Month format must be YYYY-MM")
        return self.data_dir / f"{month_text}.json"

    def load(self, month_text: str) -> list[dict[str, Any]]:
        path = self._path_for_month(month_text)
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Unable to read monthly ledger: {exc}") from exc
        if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
            raise ValueError("Monthly ledger must contain a record list")
        return [dict(item) for item in payload]

    def save(self, month_text: str, records: list[dict[str, Any]]) -> None:
        path = self._path_for_month(month_text)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_suffix(".json.tmp")
        temporary_path.write_text(
            json.dumps(records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary_path.replace(path)

