from __future__ import annotations

import argparse
import configparser
from html import escape
import json
import math
import os
import random
import re
import socket
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from post_market_ledger import StrategyLedgerDialog


CONFIG_FILE = "contracts_config.json"
APP_VERSION = "V2026.08.27"
APP_WINDOW_TITLE = f"A股ETF期权交割套利机会扫描器 {APP_VERSION}"
QMT_PORT_PROBE_TIMEOUT_SEC = 0.35
QMT_CONNECT_TIMEOUT_SEC = 4.0
QMT_SCAN_ADDR_TIMEOUT_SEC = 2.0
QMT_SECTOR_DOWNLOAD_TIMEOUT_SEC = 5.0

ARBITRAGE_MODE_DEFS: list[tuple[str, str, str]] = [
    (
        "模式1",
        "模式1 · 买入认沽 + 买入持有现货",
        "现货按卖一买入，认沽按卖一买入；主动行权认沽价卖出现货。",
    ),
    (
        "模式2",
        "模式2 · 卖出认沽 + 卖出现货",
        "现货按买一卖出，认沽按买一卖出；被动行权转入期权账户资金等待接货。",
    ),
    (
        "模式4",
        "模式4 · 买入认购 + 卖出现货",
        "现货按买一卖出，认购按卖一买入；主动行权转入期权账户资金按认购价买入现货。",
    ),
    (
        "模式3",
        "模式3 · 卖出认购+买入持有现货",
        "持有现货+卖出认购；被动行权提供现货。",
    ),
]

MODE_TIME_VALUE_REQUIREMENTS = {
    "模式1": "时间价值需为负数",
    "模式2": "时间价值需为正数",
    "模式3": "时间价值需为正数",
    "模式4": "时间价值需为负数",
}

LEDGER_PREFILL_QUOTE_FIELDS = {
    "模式1": ("mode1", "spot_ask", "option_ask"),
    "模式2": ("mode2", "spot_bid", "option_bid"),
    "模式3": ("mode3", "spot_ask", "option_bid"),
    "模式4": ("mode4", "spot_bid", "option_ask"),
}

DEFAULT_UI_POOL_FILTER_NAMES = frozenset({"50ETF", "588000ETF"})

COMPACT_CHECKBOX_STYLE = (
    "QCheckBox { font-size:11px; spacing:3px; margin:0 2px 0 0; padding:0; }"
    "QCheckBox::indicator { width:13px; height:13px; }"
)

SPOT_CHIP_STYLE_OK = (
    "background:#e8f5e9; color:#1b5e20; padding:0 3px;"
    "border-radius:2px; font-size:10px; font-weight:600;"
)
SPOT_CHIP_STYLE_BAD = (
    "background:#ffebee; color:#c62828; padding:0 3px;"
    "border-radius:2px; font-size:10px; font-weight:600;"
)

_MARKET_CONNECTION_ERROR_HINTS = (
    "连接",
    "未连接",
    "获取不到行情",
    "qmt",
    "xtquant",
    "行情失败",
    "监听端口",
    "无法解析平值",
)


def is_market_connection_error(text: str) -> bool:
    lowered = str(text or "").strip().lower()
    if not lowered:
        return False
    return any(hint in lowered for hint in _MARKET_CONNECTION_ERROR_HINTS)


def default_fee_config() -> dict[str, Any]:
    return {
        "multiplier": 10000,
        "option_open_fee": 1.7,
        "option_exercise_fee": 4.0,
        "stock_commission_rate": 0.0001,
        "stock_borrow_cost": 0.0,
        "yellow_threshold": 20.0,
        "red_threshold": 50.0,
        "alert_frequency_hz": 1200,
        "alert_duration_ms": 250,
        "alert_cooldown_sec": 3.0,
        "min_display_profit": -999999.0,
        "sound_enabled": False,
    }


def default_contract_pools() -> list[dict[str, Any]]:
    return [
        {
            "name": "50ETF",
            "spot_code": "510050.SH",
            "options": [
                {
                    "name": "50ETF 平值自动",
                    "strike": 0.0,
                    "call_code": "",
                    "put_code": "",
                    "expiry": "2026-06-24",
                    "enabled": True,
                }
            ],
        },
        {
            "name": "588000ETF",
            "spot_code": "588000.SH",
            "options": [
                {
                    "name": "588000ETF 平值自动",
                    "strike": 0.0,
                    "call_code": "",
                    "put_code": "",
                    "expiry": "2026-06-24",
                    "enabled": True,
                }
            ],
        },
        {
            "name": "300ETF",
            "spot_code": "510300.SH",
            "options": [
                {
                    "name": "300ETF 平值自动",
                    "strike": 0.0,
                    "call_code": "",
                    "put_code": "",
                    "expiry": "2026-06-24",
                    "enabled": True,
                }
            ],
        },
        {
            "name": "500ETF",
            "spot_code": "510500.SH",
            "options": [
                {
                    "name": "500ETF 平值自动",
                    "strike": 0.0,
                    "call_code": "",
                    "put_code": "",
                    "expiry": "2026-06-24",
                    "enabled": True,
                }
            ],
        },
        {
            "name": "159915",
            "spot_code": "159915.SZ",
            "options": [
                {
                    "name": "159915 平值自动",
                    "strike": 0.0,
                    "call_code": "",
                    "put_code": "",
                    "expiry": "2026-06-24",
                    "enabled": True,
                }
            ],
        },
    ]


def default_app_config() -> dict[str, Any]:
    return {
        "qmt": {
            "qmt_path": r"D:\兴业证券SMT-Q-2.0.8.0-test\userdata_mini",
            "poll_interval_ms": 500,
            "enable_mock_when_xtquant_missing": False,
            "auto_atm": True,
            "atm_refresh_sec": 300,
            "atm_strike_tiers": 5,
        },
        "fees": default_fee_config(),
        "contract_pools": default_contract_pools(),
    }


def resolve_config_path(raw_path: str) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / candidate
    return Path.cwd() / candidate


def save_app_config(path: Path, config: dict[str, Any]) -> None:
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def load_app_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        config = default_app_config()
        save_app_config(path, config)
        return config

    with path.open("r", encoding="utf-8") as file:
        config = json.load(file)

    merged = default_app_config()
    merged["qmt"].update(config.get("qmt", {}))
    merged["fees"].update(config.get("fees", {}))
    merged["contract_pools"] = config.get("contract_pools", default_contract_pools())
    return merged


@dataclass(frozen=True)
class FeeConfig:
    multiplier: int
    option_open_fee: float
    option_exercise_fee: float
    stock_commission_rate: float
    stock_borrow_cost: float
    yellow_threshold: float
    red_threshold: float
    alert_frequency_hz: int
    alert_duration_ms: int
    alert_cooldown_sec: float
    min_display_profit: float
    sound_enabled: bool

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FeeConfig":
        return cls(
            multiplier=int(data["multiplier"]),
            option_open_fee=float(data["option_open_fee"]),
            option_exercise_fee=float(data["option_exercise_fee"]),
            stock_commission_rate=float(data["stock_commission_rate"]),
            stock_borrow_cost=float(data["stock_borrow_cost"]),
            yellow_threshold=float(data["yellow_threshold"]),
            red_threshold=float(data["red_threshold"]),
            alert_frequency_hz=int(data["alert_frequency_hz"]),
            alert_duration_ms=int(data["alert_duration_ms"]),
            alert_cooldown_sec=float(data["alert_cooldown_sec"]),
            min_display_profit=float(data["min_display_profit"]),
            sound_enabled=bool(data.get("sound_enabled", True)),
        )


@dataclass(frozen=True)
class OptionPair:
    pool_name: str
    spot_code: str
    strike: float
    call_code: str
    put_code: str
    expiry: str = ""
    name: str = ""
    atm_tier: int = 0
    ref_atm_strike: float = 0.0
    is_adjusted: bool = False


ATM_TIER_LABELS: dict[int, str] = {
    0: "平值",
    1: "一档",
    2: "二档",
    3: "三档",
    4: "四档",
    5: "五档",
}


def format_atm_tier_label(tier: int) -> str:
    return ATM_TIER_LABELS.get(int(tier), f"{tier}档")


def is_adjusted_option_instrument(detail: dict[str, Any] | None) -> bool:
    """是否为调整/修改过的期权合约（名称含「调整」或行权价后缀 A，如 5604A）。"""
    if not detail:
        return False
    for field in ("InstrumentName", "ProductName"):
        text = str(detail.get(field) or "").replace(" ", "")
        if not text:
            continue
        if "调整" in text or "修改" in text:
            return True
        if re.search(r"\dA$", text, flags=re.IGNORECASE):
            return True
    return False


def option_pair_is_adjusted(xtdata: Any, call_code: str, put_code: str, *, spot_code: str = "") -> bool:
    for code in (call_code, put_code):
        if not code:
            continue
        normalized = normalize_market_code(code)
        instrument = safe_instrument_detail(xtdata, normalized)
        if is_adjusted_option_instrument(instrument):
            return True
        detail = safe_option_detail(xtdata, normalized, spot_code=spot_code)
        if is_adjusted_option_instrument(detail):
            return True
    return False


def strike_distance_tier(
    strike: float,
    ref_atm_strike: float,
    spot_code: str,
    listed_strikes: list[float] | None = None,
) -> int:
    if listed_strikes:
        index_by_strike = {value: index for index, value in enumerate(listed_strikes)}
        if strike in index_by_strike and ref_atm_strike in index_by_strike:
            return abs(index_by_strike[strike] - index_by_strike[ref_atm_strike])
    step = option_strike_step(spot_code)
    if step <= 0 or ref_atm_strike <= 0:
        return 0
    distance = abs(strike - ref_atm_strike) / step
    return int(round(distance))


@dataclass(frozen=True)
class Tick:
    bid1: float
    ask1: float
    last: float


def first_number(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (list, tuple)):
        if not value:
            return 0.0
        return first_number(value[0])
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(number) or math.isinf(number):
        return 0.0
    return number


def pick_number(data: dict[str, Any], keys: list[str]) -> float:
    for key in keys:
        if key in data:
            value = first_number(data[key])
            if value > 0:
                return value
    return 0.0


def normalize_tick(raw: Any) -> Tick | None:
    if raw is None:
        return None
    if isinstance(raw, Tick):
        return raw
    if not isinstance(raw, dict):
        return None

    bid = pick_number(raw, ["bidPrice", "bid_price", "bidPrice1", "bid1", "BidPrice1"])
    ask = pick_number(raw, ["askPrice", "ask_price", "askPrice1", "ask1", "AskPrice1"])
    last = pick_number(raw, ["lastPrice", "last_price", "last", "price", "LastPrice"])
    if last <= 0:
        last = bid or ask
    if bid <= 0 and last > 0:
        bid = last
    if ask <= 0 and last > 0:
        ask = last
    if bid <= 0 or ask <= 0:
        return None
    return Tick(bid1=bid, ask1=ask, last=last)


def build_option_pairs(contract_pools: list[dict[str, Any]], *, auto_atm: bool) -> list[OptionPair]:
    pairs: list[OptionPair] = []
    for pool in contract_pools:
        pool_name = str(pool.get("name", "")).strip()
        spot_code = str(pool.get("spot_code", "")).strip()
        if not pool_name or not spot_code:
            continue
        for option in pool.get("options", []):
            if option.get("enabled", True) is False:
                continue
            call_code = normalize_market_code(str(option.get("call_code", "")).strip())
            put_code = normalize_market_code(str(option.get("put_code", "")).strip())
            if not auto_atm and (not call_code or not put_code):
                continue
            try:
                strike = float(option.get("strike", 0) or 0)
            except (TypeError, ValueError):
                strike = 0.0
            pairs.append(
                OptionPair(
                    pool_name=pool_name,
                    spot_code=spot_code,
                    strike=strike,
                    call_code=call_code,
                    put_code=put_code,
                    expiry=str(option.get("expiry", "")).strip(),
                    name=str(option.get("name", "")).strip(),
                )
            )
    return pairs


def collect_quote_codes(pairs: list[OptionPair]) -> list[str]:
    codes: set[str] = set()
    for pair in pairs:
        if pair.spot_code:
            codes.add(pair.spot_code)
        if pair.call_code:
            codes.add(pair.call_code)
        if pair.put_code:
            codes.add(pair.put_code)
    return sorted(codes)


def collect_subscription_codes(
    templates: list[OptionPair],
    pairs: list[OptionPair] | None = None,
) -> list[str]:
    """订阅代码：已解析合约 + 配置里所有品种现货（及手动填写的期权代码）。"""
    codes: set[str] = set()
    for template in templates:
        if template.spot_code:
            codes.add(template.spot_code)
        call_code = normalize_market_code(template.call_code)
        put_code = normalize_market_code(template.put_code)
        if call_code:
            codes.add(call_code)
        if put_code:
            codes.add(put_code)
    if pairs:
        codes.update(collect_quote_codes(pairs))
    return sorted(codes)


LISTED_OPTION_SECTORS = ("上证期权", "深证期权")
SHANGHAI_OPTION_SECTOR = LISTED_OPTION_SECTORS[0]
_OPTION_SECTOR_CODES_CACHE: list[str] | None = None
_option_chain_api_error_cache: str | None | bool = False
_INSTRUMENT_STRIKE_SUFFIX_RE = re.compile(r"(\d{3,5})(?:A)?$")


def option_chain_api_error() -> str | None:
    """检测是否能在当前行情连接下解析期权链（含板块扫描兜底）。"""
    global _option_chain_api_error_cache
    if _option_chain_api_error_cache is not False:
        return _option_chain_api_error_cache or None
    try:
        from xtquant import xtdata
    except ImportError:
        _option_chain_api_error_cache = "未安装 xtquant"
        return _option_chain_api_error_cache
    try:
        for sector_name in LISTED_OPTION_SECTORS:
            sector_codes = xtdata.get_stock_list_in_sector(sector_name) or []
            if sector_codes:
                _option_chain_api_error_cache = ""
                return None
    except Exception as exc:
        _option_chain_api_error_cache = str(exc)
        return _option_chain_api_error_cache
    try:
        xtdata.get_option_list("510050.SH", "", "CALL", False)
    except TypeError as exc:
        if "NoneType" in str(exc) and "str" in str(exc):
            _option_chain_api_error_cache = (
                "无法读取上证期权板块，且 get_option_list 不可用；"
                "请确认 QMT 已登录并下载过期权板块数据。"
            )
        else:
            _option_chain_api_error_cache = str(exc)
    except Exception as exc:
        _option_chain_api_error_cache = str(exc)
    else:
        _option_chain_api_error_cache = ""
    return _option_chain_api_error_cache or None


def get_listed_option_codes(xtdata: Any) -> list[str]:
    """上证 + 深证期权板块合并列表（含 510300/510500/159915 等标的）。"""
    global _OPTION_SECTOR_CODES_CACHE
    if _OPTION_SECTOR_CODES_CACHE is not None:
        return _OPTION_SECTOR_CODES_CACHE
    merged: list[str] = []
    seen: set[str] = set()
    for sector_name in LISTED_OPTION_SECTORS:
        try:
            raw_codes = xtdata.get_stock_list_in_sector(sector_name) or []
        except Exception:
            continue
        for raw in raw_codes:
            code = normalize_market_code(str(raw))
            if code and code not in seen:
                seen.add(code)
                merged.append(code)
    _OPTION_SECTOR_CODES_CACHE = merged
    return _OPTION_SECTOR_CODES_CACHE


def get_shanghai_option_codes(xtdata: Any) -> list[str]:
    return get_listed_option_codes(xtdata)


def safe_instrument_detail(xtdata: Any, code: str) -> dict[str, Any] | None:
    if not code:
        return None
    try:
        detail = xtdata.get_instrument_detail(code)
    except Exception:
        return None
    return detail if isinstance(detail, dict) else None


def instrument_underlying_spot_code(detail: dict[str, Any]) -> str:
    product_id = str(detail.get("ProductID") or "")
    match = re.search(r"\((\d{6})\)", product_id)
    if not match:
        return ""
    short_code = match.group(1)
    if short_code.startswith(("5", "6", "9")):
        return f"{short_code}.SH"
    if short_code.startswith(("0", "1", "2", "3")):
        return f"{short_code}.SZ"
    return ""


def instrument_matches_underlying(detail: dict[str, Any], spot_code: str) -> bool:
    short_code = spot_code.split(".")[0]
    product_id = str(detail.get("ProductID") or "")
    if short_code and f"({short_code})" in product_id:
        return True
    underlying = instrument_underlying_spot_code(detail)
    return bool(underlying and underlying == spot_code)


def parse_option_side_from_name(instrument_name: str) -> str:
    name = str(instrument_name or "")
    if "沽" in name:
        return "PUT"
    if "购" in name:
        return "CALL"
    upper_name = name.upper()
    if "PUT" in upper_name or "P" == upper_name[-1:]:
        return "PUT"
    if "CALL" in upper_name or "C" == upper_name[-1:]:
        return "CALL"
    return ""


def parse_strike_from_instrument(detail: dict[str, Any], spot_code: str = "") -> float:
    for key in ("OptExercisePrice", "StrikePrice", "ExercisePrice"):
        strike = first_number(detail.get(key))
        if strike > 0:
            return strike
    name = str(detail.get("InstrumentName") or "").replace(" ", "")
    match = _INSTRUMENT_STRIKE_SUFFIX_RE.search(name)
    if not match:
        return 0.0
    raw = int(match.group(1))
    if raw >= 1000:
        return raw / 1000.0
    step = option_strike_step(spot_code) if spot_code else 0.05
    return round(raw * step, 4)


def normalize_market_code(raw_code: str) -> str:
    """与 oskhquant 一致：8 位数字期权代码补全为 .SHO / .SZO。"""
    code = str(raw_code or "").strip().upper()
    if not code:
        return ""
    if code.startswith(("SHO.", "SZO.")) and len(code) > 4:
        return f"{code[4:]}.{code[:3]}"
    if code.startswith(("SH.", "SZ.", "BJ.")) and len(code) > 3:
        prefix = code[:2]
        body = code[3:]
        if prefix in {"SH", "SZ"} and len(body) == 8 and body.isdigit():
            return f"{body}.{prefix}O"
        return f"{body}.{prefix}"
    if code.endswith((".SHO", ".SZO")):
        return code
    if code.endswith((".SH", ".SZ", ".BJ")):
        body, exchange = code.rsplit(".", 1)
        if exchange in {"SH", "SZ"} and len(body) == 8 and body.isdigit():
            return f"{body}.{exchange}O"
        return code
    if len(code) == 8 and code.isdigit():
        if code.startswith("1"):
            return f"{code}.SHO"
        if code.startswith(("5", "6", "9")):
            return f"{code}.SH"
        if code.startswith(("0", "1", "2", "3")):
            return f"{code}.SZ"
    if len(code) == 6 and code.isdigit():
        if code.startswith(("5", "6", "9")):
            return f"{code}.SH"
        if code.startswith(("0", "1", "2", "3")):
            return f"{code}.SZ"
    return code


def expiry_to_yyyymm(expiry: str) -> str:
    digits = "".join(char for char in str(expiry) if char.isdigit())
    return digits[:6] if len(digits) >= 6 else ""


def current_expiry_yyyymm() -> str:
    """Return the only expiry month used by automatic option-chain scans."""
    return time.strftime("%Y%m")


def format_expiry_date(expire_date: str | None) -> str:
    digits = "".join(char for char in str(expire_date or "") if char.isdigit())
    if len(digits) >= 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    return str(expire_date or "")


def is_active_expiry(expire_date: str) -> bool:
    digits = "".join(char for char in str(expire_date) if char.isdigit())
    if len(digits) < 8:
        return True
    return digits[:8] >= time.strftime("%Y%m%d")


def option_strike_step(spot_code: str) -> float:
    short_code = spot_code.split(".")[0]
    if short_code in {"510050", "588000", "510300", "510500", "159915"}:
        return 0.05
    return 0.05


def nearest_listed_strike(spot_price: float, spot_code: str) -> float:
    step = option_strike_step(spot_code)
    if step <= 0:
        return round(spot_price, 4)
    return round(round(spot_price / step) * step, 4)


def format_strike_display(strike: float, spot_code: str) -> str:
    step = option_strike_step(spot_code)
    decimals = 2 if step >= 0.05 else 3
    return f"{strike:.{decimals}f}"


def qmt_data_dir_from_path(qmt_path: str) -> Path:
    raw = str(qmt_path or "").strip()
    if not raw:
        return Path()
    path = Path(raw)
    lower_name = path.name.lower()
    if lower_name == "datadir":
        return path
    if lower_name in {"userdata", "userdata_mini"}:
        return path / "datadir"
    if (path / "userdata" / "datadir").exists():
        return path / "userdata" / "datadir"
    if (path / "userdata_mini" / "datadir").exists():
        return path / "userdata_mini" / "datadir"
    return path


def qmt_root_from_path(qmt_path: str) -> Path:
    raw_path = str(qmt_path or "").strip()
    if not raw_path:
        return Path()
    path = Path(raw_path)
    name = path.name.lower()
    if name == "datadir" and path.parent.name.lower() in {"userdata", "userdata_mini"}:
        return path.parent.parent
    if name in {"userdata", "userdata_mini"}:
        return path.parent
    return path


def is_mini_qmt_path(path: str) -> bool:
    normalized = str(path or "").strip().replace("/", "\\").lower()
    return normalized.endswith("\\userdata_mini") or "\\userdata_mini\\" in normalized


def resolve_qmt_path_for_options(qmt_path: str) -> str:
    """股票期权优先使用大 QMT 的 userdata，而非 userdata_mini。"""
    raw = str(qmt_path or "").strip()
    if not raw:
        return ""
    if is_mini_qmt_path(raw):
        root = qmt_root_from_path(raw)
        full_userdata = root / "userdata"
        if full_userdata.exists():
            return str(full_userdata)
    return raw


def discover_qmt_userdata_paths(*, prefer_mini: bool = False) -> list[str]:
    ordered_names = ("userdata_mini", "userdata") if prefer_mini else ("userdata", "userdata_mini")
    candidates: list[str] = []
    seen: set[str] = set()

    def add_candidate(path: Path) -> None:
        normalized = str(path or "").strip()
        if not normalized or normalized in seen:
            return
        if path.exists():
            seen.add(normalized)
            candidates.append(normalized)

    env_path = str(os.environ.get("QMT_USERDATA_PATH", "") or "").strip()
    if env_path:
        root_path = qmt_root_from_path(env_path)
        if root_path:
            for folder_name in ordered_names:
                add_candidate(root_path / folder_name)

    for static_path in (
        Path(r"D:\国金证券QMT交易端"),
        Path(r"C:\国金证券QMT交易端"),
        Path(r"D:\兴业证券SMT-Q-2.0.8.0-test"),
        Path(r"C:\兴业证券SMT-Q-2.0.8.0-test"),
    ):
        if not static_path.exists():
            continue
        for folder_name in ordered_names:
            add_candidate(static_path / folder_name)

    for drive_root in (Path("D:/"), Path("C:/")):
        if not drive_root.exists():
            continue
        try:
            entries = sorted(drive_root.iterdir(), key=lambda item: item.name.lower())
        except Exception:
            continue
        for entry in entries:
            if not entry.is_dir():
                continue
            upper_name = entry.name.upper()
            if "QMT" not in upper_name and "SMT" not in upper_name:
                continue
            for folder_name in ordered_names:
                add_candidate(entry / folder_name)
    return candidates


def resolve_qmt_path_for_connect(qmt_path: str) -> str:
    """连接行情时解析 QMT 路径：配置优先，否则自动发现大 QMT userdata。"""
    raw = str(qmt_path or "").strip()
    if raw:
        # Respect an explicit user-provided path verbatim. This matters for
        # environments where only userdata_mini has a live quote service.
        return raw
    for candidate in discover_qmt_userdata_paths(prefer_mini=False):
        if not is_mini_qmt_path(candidate):
            return candidate
    for candidate in discover_qmt_userdata_paths(prefer_mini=True):
        resolved = resolve_qmt_path_for_options(candidate) or candidate
        if resolved:
            return resolved
    return ""


def _extract_port_from_text(raw_text: str) -> int | None:
    text = str(raw_text or "").strip()
    match = re.search(r":(\d+)", text)
    if not match:
        return None
    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return None


def load_qmt_api_ports(qmt_path: str) -> dict[str, int]:
    root_path = qmt_root_from_path(qmt_path)
    if not root_path:
        return {}

    ports: dict[str, int] = {}
    xtdata_ini = root_path / "config" / "xtdata.ini"
    if xtdata_ini.exists():
        parser = configparser.ConfigParser()
        try:
            parser.read(xtdata_ini, encoding="utf-8")
            address = parser.get("client_xtdata", "address", fallback="")
            port = _extract_port_from_text(address)
            if port:
                ports["xtdata"] = port
        except Exception:
            pass

    for label, relative_path in (
        ("client", ("config", "xtclient.lua")),
        ("mini_quote", ("config", "xtminiquote.lua")),
    ):
        config_file = root_path.joinpath(*relative_path)
        if not config_file.exists():
            continue
        try:
            text = config_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        port = _extract_port_from_text(text)
        if port:
            ports[label] = port
    return ports


def ordered_qmt_market_ports(qmt_path: str) -> list[int]:
    port_info = load_qmt_api_ports(qmt_path)
    is_mini = is_mini_qmt_path(qmt_path)
    if not qmt_path:
        ordered_labels = ["xtdata", "mini_quote", "client"]
        fallback_ports = (58670, 58610, 58611, 58600)
    elif is_mini:
        ordered_labels = ["mini_quote", "xtdata", "client"]
        fallback_ports = (58610, 58611, 58670, 58600)
    else:
        # 大 QMT 常未监听 58670，但同目录 xtminiquote 的 58610 可能已启动
        ordered_labels = ["xtdata", "mini_quote", "client"]
        fallback_ports = (58670, 58610, 58611, 58600)
    ports: list[int] = []
    for label in ordered_labels:
        port = port_info.get(label)
        if port and port not in ports:
            ports.append(port)
    for fallback_port in fallback_ports:
        if fallback_port not in ports:
            ports.append(fallback_port)
    return ports


def run_with_timeout(func: Any, timeout_sec: float) -> tuple[Any | None, Exception | None]:
    result: dict[str, Any] = {}
    errors: list[Exception] = []

    def target() -> None:
        try:
            result["value"] = func()
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout_sec)
    if thread.is_alive():
        return None, TimeoutError(f"操作超时（{timeout_sec:.0f}秒）")
    if errors:
        return None, errors[0]
    return result.get("value"), None


def is_qmt_port_listening(port: int, timeout: float = QMT_PORT_PROBE_TIMEOUT_SEC) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def format_qmt_connect_error(exc: Exception) -> str:
    if isinstance(exc, ImportError) or "No module named 'xtquant'" in str(exc):
        return "未安装 xtquant，请使用 QMT 自带 Python 环境运行本程序。"
    message = str(exc or "").strip()
    if message:
        return message
    return "QMT 行情连接失败，请检查客户端是否已登录。"


def configure_xtdata_data_dir(xtdata: Any, qmt_path: str) -> None:
    data_dir = qmt_data_dir_from_path(qmt_path)
    if data_dir.exists():
        try:
            xtdata.data_dir = str(data_dir)
        except Exception:
            pass


def spot_codes_for_connect_probe(codes: list[str] | None = None) -> list[str]:
    """连接探测只用现货代码，期权盘口失败不应导致整次连接失败。"""
    fallbacks = ["510050.SH", "588000.SH", "510300.SH", "510500.SH", "159915.SZ"]
    result: list[str] = []
    for code in list(codes or []) + fallbacks:
        normalized = normalize_market_code(str(code))
        if not normalized or normalized.endswith((".SHO", ".SZO")):
            continue
        if normalized not in result:
            result.append(normalized)
    return result or ["510050.SH"]


def probe_xtdata_quote_service(
    xtdata: Any,
    probe_codes: list[str] | None = None,
    *,
    require_all: bool = False,
) -> bool:
    codes = spot_codes_for_connect_probe(probe_codes)
    if not codes:
        return False

    ok_count = 0
    for code in codes:
        try:
            ticks = xtdata.get_full_tick([code])
        except Exception:
            if require_all:
                return False
            continue
        if isinstance(ticks, dict) and normalize_tick(ticks.get(code)) is not None:
            ok_count += 1
        elif require_all:
            return False
    if require_all:
        return ok_count == len(codes)
    return ok_count > 0


def explain_qmt_market_port_failure(qmt_path: str, port_errors: list[dict[str, str]]) -> str:
    port_info = load_qmt_api_ports(qmt_path)
    is_mini = is_mini_qmt_path(qmt_path)
    xtdata_port = port_info.get("xtdata", 58610 if is_mini else 58670)
    mini_quote_port = port_info.get("mini_quote", 58610)
    client_port = port_info.get("client", 58600 if qmt_path else None)

    def _match_port(target_port: int | None, *needles: str) -> bool:
        if target_port is None:
            return False
        return any(
            int(item.get("port", -1)) == target_port and any(needle in item.get("error", "") for needle in needles)
            for item in port_errors
        )

    xtdata_missing = _match_port(xtdata_port, "无法连接xtquant服务")
    mini_missing = _match_port(mini_quote_port, "无法连接xtquant服务", "未取到有效行情")
    client_unsupported = _match_port(client_port, "200005", "未找到处理函数", "未取到有效行情")

    if xtdata_missing and client_unsupported and mini_missing:
        return (
            f"大QMT 行情端口 {xtdata_port} 未启动，交易端口 {client_port} 不支持行情；"
            f"mini 行情端口 {mini_quote_port} 也未返回有效数据。"
            "请先登录大QMT「行情+交易」模式，或同时启动 miniQMT 并登录后再试。"
        )
    if xtdata_missing and client_unsupported:
        return (
            f"大QMT 配置的 xtdata 端口 {xtdata_port} 未启动；端口 {client_port} 虽可连但不支持 get_full_tick（错误 200005）。"
            "请改用「行情+交易登录」，或保持 miniQMT 已登录（程序会尝试 58610 行情端口）。"
        )
    if xtdata_missing:
        return (
            f"未检测到 QMT xtdata 行情端口 {xtdata_port}。"
            "请启动大QMT 并开启行情+交易登录；若仅开了交易端，可同时登录 miniQMT 提供 58610 行情。"
        )
    if client_unsupported:
        return (
            f"端口 {client_port} 为交易/公式接口，不支持行情 API。"
            "请勿只连交易端口；请启动带行情的客户端（大QMT 58670 或 miniQMT 58610）。"
        )
    if port_errors:
        attempts = "；".join(f"{item['port']}: {item['error']}" for item in port_errors[:4])
        return f"QMT 行情连接失败：{attempts}"
    return "QMT 行情连接失败，请检查客户端登录模式、版本和本地监听端口。"


def connect_xtdata(qmt_path: str, probe_codes: list[str] | None = None) -> tuple[Any, str]:
    global _OPTION_SECTOR_CODES_CACHE
    _OPTION_SECTOR_CODES_CACHE = None
    try:
        from xtquant import xtdata
    except ImportError as exc:
        raise ConnectionError(format_qmt_connect_error(exc)) from exc

    try:
        from xtquant import xtconn
    except ImportError:
        xtconn = None

    resolved_path = resolve_qmt_path_for_connect(qmt_path)
    if hasattr(xtdata, "enable_hello"):
        xtdata.enable_hello = False
    configure_xtdata_data_dir(xtdata, resolved_path)
    connect_probes = spot_codes_for_connect_probe(probe_codes)

    def _reuse_existing() -> str | None:
        try:
            if xtdata.get_client() is None:
                return None
        except Exception:
            return None
        ok, probe_err = run_with_timeout(
            lambda: probe_xtdata_quote_service(xtdata, connect_probes),
            QMT_CONNECT_TIMEOUT_SEC,
        )
        if probe_err is not None:
            return None
        if ok:
            return "复用现有连接"
        return None

    reuse_note, reuse_err = run_with_timeout(_reuse_existing, QMT_CONNECT_TIMEOUT_SEC)
    if reuse_err is None and reuse_note:
        return xtdata, reuse_note

    port_errors: list[dict[str, str]] = []
    candidate_ports = list(ordered_qmt_market_ports(resolved_path))
    scanned_addrs: list[str] = []

    def _scan_addrs() -> None:
        if xtconn is None:
            return
        scanned_addrs.extend(xtconn.scan_available_server_addr())

    run_with_timeout(_scan_addrs, QMT_SCAN_ADDR_TIMEOUT_SEC)
    for addr in scanned_addrs:
        try:
            _, port_text = str(addr).split(":")
            port = int(port_text)
            if port not in candidate_ports:
                candidate_ports.append(port)
        except Exception:
            continue
    for port in (58670, 58610, 58611, 58600):
        if port not in candidate_ports:
            candidate_ports.append(port)

    for port in candidate_ports:
        if not is_qmt_port_listening(port):
            port_errors.append({"port": str(port), "error": "端口未监听"})
            continue

        def _attempt_port() -> int:
            if hasattr(xtdata, "disconnect"):
                xtdata.disconnect()
            if hasattr(xtdata, "connect"):
                xtdata.connect("127.0.0.1", port, False)
            configure_xtdata_data_dir(xtdata, resolved_path)
            if probe_xtdata_quote_service(xtdata, connect_probes):
                return port
            raise RuntimeError("已连接但未取到有效行情")

        result, attempt_err = run_with_timeout(_attempt_port, QMT_CONNECT_TIMEOUT_SEC)
        if attempt_err is not None:
            port_errors.append({"port": str(port), "error": str(attempt_err)})
            continue
        path_note = f"，路径 {resolved_path}" if resolved_path else ""
        return xtdata, f"连接端口 {result}{path_note}"

    raise ConnectionError(explain_qmt_market_port_failure(resolved_path, port_errors))


def spot_reference_price(tick: Tick | None, spot_code: str) -> float:
    if tick is not None:
        if tick.last > 0:
            return tick.last
        if tick.bid1 > 0 and tick.ask1 > 0:
            return (tick.bid1 + tick.ask1) / 2
        if tick.bid1 > 0:
            return tick.bid1
        if tick.ask1 > 0:
            return tick.ask1

    try:
        from xtquant import xtdata

        detail = xtdata.get_instrument_detail(spot_code)
        if isinstance(detail, dict):
            for key in ("PreClose", "SettlementPrice", "LastPrice"):
                value = first_number(detail.get(key))
                if value > 0:
                    return value
    except Exception:
        pass
    return 0.0


def quote_mid_price(tick: Tick | None) -> float:
    if tick is None:
        return 0.0
    if tick.bid1 > 0 and tick.ask1 > 0:
        return (tick.bid1 + tick.ask1) / 2
    if tick.last > 0:
        return tick.last
    return tick.bid1 or tick.ask1 or 0.0


def option_intrinsic_time_value(
    spot_price: float,
    strike: float,
    option_price: float,
    *,
    is_call: bool,
) -> tuple[float, float]:
    """期权内在价值、时间价值（按现货/期权中间价估算）。"""
    if spot_price <= 0 or strike <= 0 or option_price < 0:
        return 0.0, 0.0
    if is_call:
        intrinsic = max(spot_price - strike, 0.0)
    else:
        intrinsic = max(strike - spot_price, 0.0)
    time_value = option_price - intrinsic
    return intrinsic, time_value


def option_moneyness_text(spot_price: float, strike: float, *, is_call: bool) -> str:
    if spot_price <= 0 or strike <= 0:
        return "价格未知"
    epsilon = 0.001
    diff = spot_price - strike
    if abs(diff) <= epsilon:
        return "行权价接近现价"
    return "行权价低于现价" if diff > 0 else "行权价高于现价"


def option_is_in_the_money(spot_price: float, strike: float, *, is_call: bool) -> bool:
    """Keep option-specific in-the-money logic independent from UI wording."""
    if spot_price <= 0 or strike <= 0:
        return False
    return spot_price > strike if is_call else spot_price < strike


def option_exercise_status_text(
    spot_price: float,
    strike: float,
    *,
    is_call: bool,
    is_long_option: bool,
) -> str:
    """Describe the current moneyness and the matching expiry exercise outcome."""
    side = ("买入" if is_long_option else "卖出") + ("认购" if is_call else "认沽")
    if spot_price <= 0 or strike <= 0:
        return f"{side}：行权状态未知"
    if abs(spot_price - strike) <= 0.001:
        action = "是否主动行权" if is_long_option else "到期是否行权"
        return f"{side}：近平值；{action}取决于结算价"

    is_in_the_money = option_is_in_the_money(spot_price, strike, is_call=is_call)
    if is_long_option:
        if is_in_the_money:
            outcome = "需主动行权买入现货回补" if is_call else "需主动行权卖出现货"
            return f"{side}：实值；若到期维持，{outcome}"
        return f"{side}：虚值；若到期维持，通常无需主动行权"

    if is_in_the_money:
        outcome = "可能被行权交券" if is_call else "可能被行权接货"
        return f"{side}：实值；若到期维持，{outcome}"
    return f"{side}：虚值；若到期维持，通常不行权"


def recommendation_effective_profit(row: dict[str, Any]) -> float:
    profit = float(row.get("profit", 0.0))
    if bool(row.get("alert_eligible")):
        return profit

    upper_profit = row.get("exercise_upper_profit")
    if bool(row.get("is_in_the_money")) and upper_profit is not None:
        return float(upper_profit)
    return float("-inf")


def recommendation_profit_label(row: dict[str, Any]) -> str:
    if bool(row.get("alert_eligible")):
        return "保底收益"
    if bool(row.get("is_in_the_money")) and row.get("exercise_upper_profit") is not None:
        return "若被行权收益"
    return str(row.get("profit_type", ""))


def recommendation_rank_key(row: dict[str, Any]) -> tuple[int, float, int, float]:
    effective_profit = recommendation_effective_profit(row)
    if effective_profit == float("-inf") or effective_profit <= 0:
        return (9, 0.0, 9, 0.0)

    moneyness_priority = 0 if bool(row.get("is_in_the_money")) else 1
    certainty_priority = 0 if bool(row.get("alert_eligible")) else 1
    return (moneyness_priority, -effective_profit, certainty_priority, -float(row.get("profit", 0.0)))


def sort_mode_rows_by_strike(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Order mode-table rows by numeric strike without affecting recommendations."""
    return sorted(rows, key=lambda row: (float(row.get("strike", 0.0)), str(row.get("option_code", ""))))


def select_atm_pairs_for_status(pairs: list[OptionPair]) -> list[OptionPair]:
    """Keep one actual ATM pair per underlying for the status summary."""
    selected: dict[str, OptionPair] = {}
    for pair in pairs:
        current = selected.get(pair.spot_code)
        if current is None:
            selected[pair.spot_code] = pair
            continue
        current_rank = (
            0 if current.atm_tier == 0 else 1,
            abs(current.strike - current.ref_atm_strike) if current.ref_atm_strike > 0 else 0.0,
            current.strike,
        )
        candidate_rank = (
            0 if pair.atm_tier == 0 else 1,
            abs(pair.strike - pair.ref_atm_strike) if pair.ref_atm_strike > 0 else 0.0,
            pair.strike,
        )
        if candidate_rank < current_rank:
            selected[pair.spot_code] = pair
    return [selected[spot_code] for spot_code in sorted(selected)]


def build_recommendations(rows: list[dict[str, Any]], limit: int = 3) -> list[dict[str, Any]]:
    max_count = max(0, int(limit))
    if max_count == 0:
        return []

    candidates = [
        row
        for row in rows
        if recommendation_effective_profit(row) != float("-inf")
        and recommendation_effective_profit(row) > 0
    ]
    candidates.sort(key=recommendation_rank_key)
    return candidates[:max_count]


def recommendation_guidance_text(rows: list[dict[str, Any]]) -> str:
    """Return concise trading heuristics and any current active-call reminder."""
    lines = [
        "交易提示：买入认沽/买入认购（模式1、4）通常优先选择时间价值为负；"
        "卖出认沽/卖出认购（模式2、3）通常优先选择时间价值为正。仅作筛选参考，不是绝对条件。",
        "经验提醒：模式1、4买入期权，实值时需要主动行权；模式2、3卖出期权，实值时才可能被对手行权。",
        "主动行权提示：模式4买入认购若实值且时间价值为负，主动行权收益可能明显高于不行权结果，"
        "达到约70元/张时优先核对主动行权条件。",
    ]

    high_return_calls = [
        row
        for row in rows
        if str(row.get("mode_key", "")) == "模式4"
        and bool(row.get("is_in_the_money"))
        and float(row.get("time_value", 0.0)) < 0
        and float(row.get("profit", 0.0)) >= 70.0
    ]
    if high_return_calls:
        best = max(high_return_calls, key=lambda row: float(row.get("profit", 0.0)))
        lines.append(
            "当前提醒：模式4买入认购主动行权口径约 "
            f"{float(best.get('profit', 0.0)):.2f} 元/张，优先核对主动行权条件。"
        )
    return "\n".join(lines)


def recommendation_guidance_html(rows: list[dict[str, Any]]) -> str:
    """Render guidance with red emphasis for active-exercise reminders."""
    rendered_lines = []
    for line in recommendation_guidance_text(rows).splitlines():
        is_active_exercise = line.startswith(("主动行权提示", "当前提醒"))
        if is_active_exercise:
            rendered_lines.append(
                f'<span style="color:#b91c1c;font-weight:600;">{escape(line)}</span>'
            )
        else:
            rendered_lines.append(f'<span style="color:#174a72;">{escape(line)}</span>')
    return "<br>".join(rendered_lines)


FORMULA_EXPLANATION_TEXT = """
模式1 买入认沽 + 买入现货
保底收益 = 现货买入成本按卖一 + 认沽买入成本按卖一 + 买入开仓费1.7 + 主动行权费4 之后，
在到期最差按K卖出现货时的保底结果。

公式：
K×10000 - [现货卖一×10000×(1+佣金率) + 认沽卖一×10000 + 买入开仓费 + 主动行权费]

模式2 卖出认沽 + 卖出现货
每张收益(元) = 未被行权估算。
假设卖出认沽开仓不收费，且最终未被行权，然后按现货卖一回补恢复头寸。

公式：
现货买一×10000×(1-佣金率) + 认沽买一×10000 - 现货卖一×10000×(1+佣金率)

若被行权收益 = 若到期买方最终行权，你按K被动接货时的收益。

公式：
现货买一×10000×(1-佣金率) + 认沽买一×10000 - K×10000

模式3 卖出认购 + 持有现货
每张收益(元) = 未被行权估算。
假设卖出认购开仓不收费，且最终未被行权，然后按现货买一卖出现货落袋。

公式：
现货买一×10000×(1-佣金率) + 认购买一×10000 - 现货卖一×10000×(1+佣金率)

若被行权收益 = 若到期买方最终行权，你按K被动交券时的收益。

公式：
K×10000 + 认购买一×10000 - 现货卖一×10000×(1+佣金率)

模式4 买入认购 + 卖出现货
保底收益 = 现货卖出后，未来最差按K主动行权买回现货，再扣买入开仓费1.7和主动行权费4后的保底结果。

公式：
现货买一×10000×(1-佣金率)
- [K×10000 + 认购卖一×10000 + 买入开仓费 + 主动行权费 + 融券成本]
""".strip()


def safe_option_detail(xtdata: Any, code: str, *, spot_code: str = "") -> dict[str, Any] | None:
    if not code:
        return None
    normalized = normalize_market_code(code)
    try:
        detail = xtdata.get_option_detail_data(code)
        if isinstance(detail, dict) and detail:
            strike = first_number(detail.get("OptExercisePrice"))
            if strike > 0:
                return detail
    except Exception:
        pass

    instrument = safe_instrument_detail(xtdata, normalized)
    if not instrument:
        return None
    underlying = instrument_underlying_spot_code(instrument) or spot_code
    strike = parse_strike_from_instrument(instrument, underlying)
    if strike <= 0:
        return None
    return {
        "OptExercisePrice": strike,
        "ExpireDate": instrument.get("ExpireDate"),
        "InstrumentName": instrument.get("InstrumentName"),
        "ProductID": instrument.get("ProductID"),
    }


def _gather_option_strike_pairs_from_api(
    xtdata: Any,
    spot_code: str,
    expiry_yyyymm: str,
) -> tuple[dict[float, str], dict[float, str], dict[float, str]]:
    calls_by_strike: dict[float, str] = {}
    puts_by_strike: dict[float, str] = {}
    expiry_by_strike: dict[float, str] = {}

    for opt_type, target in (("CALL", calls_by_strike), ("PUT", puts_by_strike)):
        try:
            codes = xtdata.get_option_list(spot_code, expiry_yyyymm, opt_type, False) or []
        except Exception:
            codes = []
        for code in codes:
            if not code:
                continue
            detail = safe_option_detail(xtdata, str(code), spot_code=spot_code)
            if not detail or is_adjusted_option_instrument(detail):
                continue
            strike = first_number(detail.get("OptExercisePrice"))
            expire = str(detail.get("ExpireDate") or "")
            if strike <= 0 or not is_active_expiry(expire):
                continue
            if expiry_yyyymm and not expire.startswith(expiry_yyyymm):
                continue
            target[strike] = normalize_market_code(str(code))
            expiry_by_strike.setdefault(strike, expire)

    return calls_by_strike, puts_by_strike, expiry_by_strike


def _gather_option_strike_pairs_from_sector(
    xtdata: Any,
    spot_code: str,
    expiry_yyyymm: str,
) -> tuple[dict[float, str], dict[float, str], dict[float, str]]:
    """miniQMT 行情口常用：扫描「上证期权」板块 + get_instrument_detail 解析平值。"""
    calls_by_strike: dict[float, str] = {}
    puts_by_strike: dict[float, str] = {}
    expiry_by_strike: dict[float, str] = {}

    for code in get_listed_option_codes(xtdata):
        instrument = safe_instrument_detail(xtdata, code)
        if not instrument or is_adjusted_option_instrument(instrument):
            continue
        if not instrument_matches_underlying(instrument, spot_code):
            continue
        expire = str(instrument.get("ExpireDate") or "")
        if not is_active_expiry(expire):
            continue
        if expiry_yyyymm and not expire.startswith(expiry_yyyymm):
            continue
        strike = parse_strike_from_instrument(instrument, spot_code)
        if strike <= 0:
            continue
        side = parse_option_side_from_name(str(instrument.get("InstrumentName") or ""))
        if side == "CALL":
            calls_by_strike[strike] = code
        elif side == "PUT":
            puts_by_strike[strike] = code
        else:
            continue
        expiry_by_strike.setdefault(strike, expire)

    return calls_by_strike, puts_by_strike, expiry_by_strike


def _gather_option_strike_pairs(
    xtdata: Any,
    spot_code: str,
    expiry_yyyymm: str,
) -> tuple[dict[float, str], dict[float, str], dict[float, str]]:
    calls, puts, expiry = _gather_option_strike_pairs_from_api(xtdata, spot_code, expiry_yyyymm)
    if calls and puts:
        return calls, puts, expiry
    sector_calls, sector_puts, sector_expiry = _gather_option_strike_pairs_from_sector(
        xtdata,
        spot_code,
        expiry_yyyymm,
    )
    if not calls:
        calls = sector_calls
    if not puts:
        puts = sector_puts
    if not expiry:
        expiry = sector_expiry
    return calls, puts, expiry


def _pick_best_strike_pair(
    spot_price: float,
    calls_by_strike: dict[float, str],
    puts_by_strike: dict[float, str],
    expiry_by_strike: dict[float, str],
) -> tuple[str, str, float, str] | None:
    common = sorted(set(calls_by_strike) & set(puts_by_strike))
    if not common:
        return None

    best_strike = min(common, key=lambda strike: abs(strike - spot_price))
    call_code = calls_by_strike[best_strike]
    put_code = puts_by_strike[best_strike]
    expire = format_expiry_date(expiry_by_strike.get(best_strike, ""))

    try:
        from xtquant import xtdata

        for code in (call_code, put_code):
            detail = safe_option_detail(xtdata, code, spot_code=spot_code)
            if detail:
                strike_from_detail = first_number(detail.get("OptExercisePrice"))
                if strike_from_detail > 0:
                    best_strike = strike_from_detail
                    break
    except Exception:
        pass

    return (
        normalize_market_code(call_code),
        normalize_market_code(put_code),
        best_strike,
        expire,
    )


def pick_strike_ladder_for_underlying(
    spot_code: str,
    spot_price: float,
    expiry_yyyymm: str = "",
    *,
    max_tiers: int = 5,
) -> list[tuple[str, str, float, str, int, float]]:
    """返回 [(call, put, strike, expiry, atm_tier, ref_atm_strike), ...]，含平值及上下 max_tiers 档。"""
    try:
        from xtquant import xtdata
    except ImportError:
        return []

    if hasattr(xtdata, "download_sector_data"):
        _, download_err = run_with_timeout(xtdata.download_sector_data, QMT_SECTOR_DOWNLOAD_TIMEOUT_SEC)
        del download_err

    month_filters = [expiry_yyyymm or current_expiry_yyyymm()]

    max_tiers = max(0, int(max_tiers))
    for month_filter in month_filters:
        calls_by_strike, puts_by_strike, expiry_by_strike = _gather_option_strike_pairs(
            xtdata,
            spot_code,
            month_filter,
        )
        common = sorted(set(calls_by_strike) & set(puts_by_strike))
        if not common:
            continue

        ref_atm_strike = min(common, key=lambda strike: abs(strike - spot_price))
        ladder: list[tuple[str, str, float, str, int, float]] = []
        for strike in common:
            tier = strike_distance_tier(strike, ref_atm_strike, spot_code, common)
            if tier > max_tiers:
                continue
            call_code = normalize_market_code(calls_by_strike[strike])
            put_code = normalize_market_code(puts_by_strike[strike])
            if option_pair_is_adjusted(xtdata, call_code, put_code, spot_code=spot_code):
                continue
            expire = format_expiry_date(expiry_by_strike.get(strike, ""))
            ladder.append(
                (
                    call_code,
                    put_code,
                    strike,
                    expire,
                    tier,
                    ref_atm_strike,
                )
            )
        ladder.sort(key=lambda item: (item[4], item[2]))
        if ladder:
            return ladder
    return []


def pick_atm_for_underlying(spot_code: str, spot_price: float, expiry_yyyymm: str = "") -> tuple[str, str, float, str] | None:
    try:
        from xtquant import xtdata
    except ImportError:
        return None

    if hasattr(xtdata, "download_sector_data"):
        _, download_err = run_with_timeout(xtdata.download_sector_data, QMT_SECTOR_DOWNLOAD_TIMEOUT_SEC)
        del download_err

    month_filters = [expiry_yyyymm or current_expiry_yyyymm()]

    for month_filter in month_filters:
        calls_by_strike, puts_by_strike, expiry_by_strike = _gather_option_strike_pairs(
            xtdata,
            spot_code,
            month_filter,
        )
        picked = _pick_best_strike_pair(spot_price, calls_by_strike, puts_by_strike, expiry_by_strike)
        if picked:
            return picked
    return None


def find_option_by_strike(
    spot_code: str,
    strike: float,
    opt_type: str,
    expiry_yyyymm: str = "",
) -> str | None:
    try:
        from xtquant import xtdata
    except ImportError:
        return None

    calls, puts, _ = _gather_option_strike_pairs(xtdata, spot_code, expiry_yyyymm)
    target = calls if opt_type.upper() == "CALL" else puts
    code = target.get(strike)
    if code:
        return code
    for option_strike, option_code in target.items():
        if abs(option_strike - strike) < 0.001:
            return option_code
    return None


def resolve_manual_option_pair(template: OptionPair) -> OptionPair | None:
    call_code = normalize_market_code(template.call_code)
    put_code = normalize_market_code(template.put_code)
    if call_code and put_code:
        strike = template.strike
        if strike <= 0:
            try:
                from xtquant import xtdata

                detail = safe_option_detail(xtdata, call_code, spot_code=template.spot_code) or safe_option_detail(
                    xtdata, put_code, spot_code=template.spot_code
                )
                if detail:
                    strike = first_number(detail.get("OptExercisePrice"))
            except Exception:
                pass
        return OptionPair(
            pool_name=template.pool_name,
            spot_code=template.spot_code,
            strike=strike,
            call_code=call_code,
            put_code=put_code,
            expiry=template.expiry,
            name=template.name,
        )

    known_code = call_code or put_code
    if not known_code:
        return None

    try:
        from xtquant import xtdata
    except ImportError:
        return None

    detail = safe_option_detail(xtdata, known_code, spot_code=template.spot_code)
    if not detail:
        return None

    strike = first_number(detail.get("OptExercisePrice"))
    if strike <= 0:
        return None

    expiry = format_expiry_date(str(detail.get("ExpireDate") or "")) or template.expiry
    yyyymm = expiry_to_yyyymm(expiry or template.expiry)
    instrument_name = str(detail.get("InstrumentName") or template.name)

    if call_code:
        paired_put = find_option_by_strike(template.spot_code, strike, "PUT", yyyymm)
        if not paired_put:
            return None
        return OptionPair(
            pool_name=template.pool_name,
            spot_code=template.spot_code,
            strike=strike,
            call_code=call_code,
            put_code=paired_put,
            expiry=expiry,
            name=template.name or instrument_name,
        )

    paired_call = find_option_by_strike(template.spot_code, strike, "CALL", yyyymm)
    if not paired_call:
        return None
    return OptionPair(
        pool_name=template.pool_name,
        spot_code=template.spot_code,
        strike=strike,
        call_code=paired_call,
        put_code=put_code,
        expiry=expiry,
        name=template.name or instrument_name,
    )


def resolve_atm_pairs(
    templates: list[OptionPair],
    ticks: dict[str, Tick],
    *,
    auto_atm: bool,
    use_mock: bool,
    max_tiers: int = 5,
) -> list[OptionPair]:
    resolved: list[OptionPair] = []
    for template in templates:
        if template.call_code or template.put_code:
            manual = resolve_manual_option_pair(template)
            if manual:
                try:
                    from xtquant import xtdata

                    is_adjusted = option_pair_is_adjusted(
                        xtdata,
                        manual.call_code,
                        manual.put_code,
                        spot_code=manual.spot_code,
                    )
                except ImportError:
                    is_adjusted = False
                if is_adjusted != manual.is_adjusted:
                    manual = OptionPair(
                        pool_name=manual.pool_name,
                        spot_code=manual.spot_code,
                        strike=manual.strike,
                        call_code=manual.call_code,
                        put_code=manual.put_code,
                        expiry=manual.expiry,
                        name=manual.name,
                        atm_tier=manual.atm_tier,
                        ref_atm_strike=manual.ref_atm_strike,
                        is_adjusted=is_adjusted,
                    )
                resolved.append(manual)
                continue

        if not auto_atm:
            continue

        spot_price = spot_reference_price(ticks.get(template.spot_code), template.spot_code)
        if spot_price <= 0 and use_mock:
            spot_price = 1.0
        if spot_price <= 0:
            continue

        yyyymm = current_expiry_yyyymm()
        ladder = pick_strike_ladder_for_underlying(
            template.spot_code,
            spot_price,
            yyyymm,
            max_tiers=max_tiers,
        )
        if ladder:
            for call_code, put_code, strike, expiry, tier, ref_atm in ladder:
                tier_label = format_atm_tier_label(tier)
                resolved.append(
                    OptionPair(
                        pool_name=template.pool_name,
                        spot_code=template.spot_code,
                        strike=strike,
                        call_code=call_code,
                        put_code=put_code,
                        expiry=expiry or template.expiry,
                        name=template.name
                        or f"{tier_label} {format_strike_display(strike, template.spot_code)}",
                        atm_tier=tier,
                        ref_atm_strike=ref_atm,
                        is_adjusted=False,
                    )
                )
            continue

        picked = pick_atm_for_underlying(template.spot_code, spot_price, yyyymm)
        if picked:
            call_code, put_code, strike, expiry = picked
            resolved.append(
                OptionPair(
                    pool_name=template.pool_name,
                    spot_code=template.spot_code,
                    strike=strike,
                    call_code=call_code,
                    put_code=put_code,
                    expiry=expiry or template.expiry,
                    name=template.name or f"平值 {format_strike_display(strike, template.spot_code)}",
                    atm_tier=0,
                    ref_atm_strike=strike,
                )
            )
            continue

        if use_mock:
            ref_strike = nearest_listed_strike(spot_price, template.spot_code)
            step = option_strike_step(template.spot_code)
            short_code = template.spot_code.split(".")[0]
            seen: set[float] = set()
            for tier in range(max(0, int(max_tiers)) + 1):
                tier_strikes = [ref_strike] if tier == 0 else [ref_strike + tier * step, ref_strike - tier * step]
                for strike in tier_strikes:
                    if strike <= 0 or strike in seen:
                        continue
                    seen.add(strike)
                    call_code = normalize_market_code(template.call_code) or f"MOCK_CALL_{short_code}_{strike:.2f}"
                    put_code = normalize_market_code(template.put_code) or f"MOCK_PUT_{short_code}_{strike:.2f}"
                    resolved.append(
                        OptionPair(
                            pool_name=template.pool_name,
                            spot_code=template.spot_code,
                            strike=strike,
                            call_code=call_code,
                            put_code=put_code,
                            expiry=template.expiry,
                            name=template.name
                            or f"{format_atm_tier_label(tier)} {format_strike_display(strike, template.spot_code)}",
                            atm_tier=tier,
                            ref_atm_strike=ref_strike,
                        )
                    )
    return resolved


def pairs_from_templates(templates: list[OptionPair]) -> list[OptionPair]:
    """从配置模板提取可展示的合约（含手动填写的认购/认沽代码）。"""
    pairs: list[OptionPair] = []
    for template in templates:
        call_code = normalize_market_code(template.call_code)
        put_code = normalize_market_code(template.put_code)
        if not call_code and not put_code:
            continue
        pairs.append(
            OptionPair(
                pool_name=template.pool_name,
                spot_code=template.spot_code,
                strike=template.strike,
                call_code=call_code,
                put_code=put_code,
                expiry=template.expiry,
                name=template.name,
            )
        )
    return pairs


def build_market_status(
    templates: list[OptionPair],
    pairs: list[OptionPair],
    ticks: dict[str, Tick],
    *,
    error: str = "",
) -> dict[str, Any]:
    spot_codes = sorted({template.spot_code for template in templates})
    spots: dict[str, Any] = {}
    for code in spot_codes:
        tick = ticks.get(code)
        spots[code] = {
            "bid": tick.bid1 if tick else None,
            "ask": tick.ask1 if tick else None,
            "price": spot_reference_price(tick, code) if tick else None,
            "ok": tick is not None,
        }

    display_pairs = pairs if pairs else pairs_from_templates(templates)
    status_pairs = select_atm_pairs_for_status(display_pairs)
    contracts: dict[str, Any] = {}
    for pair in status_pairs:
        contracts[pair.spot_code] = {
            "pool": pair.pool_name,
            "strike": pair.strike,
            "call": pair.call_code,
            "put": pair.put_code,
            "expiry": pair.expiry,
            "name": pair.name,
            "call_ok": ticks.get(pair.call_code) is not None if pair.call_code else False,
            "put_ok": ticks.get(pair.put_code) is not None if pair.put_code else False,
            "atm_pending": False,
        }
    chain_error = ""
    if any(
        not normalize_market_code(template.call_code) and not normalize_market_code(template.put_code)
        for template in templates
    ):
        chain_error = option_chain_api_error() or ""
    for template in templates:
        if template.spot_code in contracts:
            continue
        call_code = normalize_market_code(template.call_code)
        put_code = normalize_market_code(template.put_code)
        contracts[template.spot_code] = {
            "pool": template.pool_name,
            "strike": template.strike,
            "call": call_code or "-",
            "put": put_code or "-",
            "expiry": template.expiry,
            "name": template.name,
            "call_ok": bool(call_code) and ticks.get(call_code) is not None,
            "put_ok": bool(put_code) and ticks.get(put_code) is not None,
            "atm_pending": not call_code and not put_code,
            "chain_error": chain_error or "",
        }

    option_total = 0
    option_ok = 0
    for pair in display_pairs:
        for code in (pair.call_code, pair.put_code):
            if not code:
                continue
            option_total += 1
            if ticks.get(code) is not None:
                option_ok += 1

    return {
        "spots": spots,
        "contracts": contracts,
        "option_total": option_total,
        "option_ok": option_ok,
        "error": str(error or "").strip(),
    }


def format_code_short(code: str) -> str:
    normalized = normalize_market_code(code)
    if not normalized:
        return code
    if normalized.endswith((".SHO", ".SZO")):
        body, exchange = normalized.rsplit(".", 1)
        return f"{body}.{exchange}"
    return normalized.split(".")[0]


def format_spot_quotes_text(status: dict[str, Any]) -> str:
    error = str(status.get("error") or "").strip()
    parts: list[str] = []
    for code, quote in status.get("spots", {}).items():
        short_code = format_code_short(code)
        if quote.get("ok"):
            parts.append(f"{short_code} 买 {quote['bid']:.4f} / 卖 {quote['ask']:.4f}")
        else:
            parts.append(f"{short_code} 获取不到行情")

    option_total = int(status.get("option_total", 0))
    option_ok = int(status.get("option_ok", 0))
    if option_total:
        if option_ok < option_total:
            parts.append(f"期权盘口 {option_ok}/{option_total} 有效（部分获取不到行情）")
        else:
            parts.append(f"期权盘口 {option_ok}/{option_total} 有效")

    if error and not any(quote.get("ok") for quote in status.get("spots", {}).values()):
        return f"现货行情：获取不到行情 — {error}"
    if error:
        parts.append(error)
    return "现货行情：" + ("  |  ".join(parts) if parts else "等待 QMT...")


def format_contract_targets_text(status: dict[str, Any]) -> str:
    contracts = status.get("contracts", {})
    if not contracts:
        return "当前平值合约：尚未解析（请确认 QMT 已连接且期权链可用，或手动填写认购/认沽代码）"

    lines: list[str] = ["当前平值合约（行权价 / 认购 / 认沽）："]
    for spot_code in sorted(contracts):
        info = contracts[spot_code]
        short_code = format_code_short(spot_code)
        pool = str(info.get("pool") or short_code)
        strike = first_number(info.get("strike"))
        strike_text = format_strike_display(strike, spot_code) if strike > 0 else "-"
        call_code = str(info.get("call") or "-")
        put_code = str(info.get("put") or "-")
        expiry = str(info.get("expiry") or "-")
        mock_flag = "【模拟】" if call_code.startswith("MOCK_") or put_code.startswith("MOCK_") else ""
        if info.get("atm_pending"):
            spot_ok = bool(status.get("spots", {}).get(spot_code, {}).get("ok"))
            spot_hint = "现货有行情" if spot_ok else "现货获取不到行情"
            chain_hint = str(
                info.get("chain_error") or "自动平值未解析（请检查到期日或手动填写认购/认沽代码）"
            )
            lines.append(f"  · {pool}（{short_code}）{mock_flag}  {spot_hint}，{chain_hint}")
            continue
        call_quote = "有盘口" if info.get("call_ok") else "获取不到行情"
        put_quote = "有盘口" if info.get("put_ok") else "获取不到行情"
        lines.append(
            f"  · {pool}（{short_code}）{mock_flag}  行权价 {strike_text}  到期 {expiry}"
        )
        lines.append(f"      认购 {call_code}（{call_quote}）")
        lines.append(f"      认沽 {put_code}（{put_quote}）")
    return "\n".join(lines)


CONTRACT_TABLE_HEADERS = [
    "品种",
    "现货代码",
    "现货实时价",
    "行权价",
    "到期",
    "认购",
    "认沽",
    "认购盘口",
    "认沽盘口",
]


def _quote_status_text(ok: bool) -> str:
    return "正常" if ok else "无行情"


def _apply_table_status_item(item: QTableWidgetItem, ok: bool) -> None:
    if ok:
        item.setForeground(QColor("#1b5e20"))
    else:
        item.setForeground(QColor("#c62828"))


def format_worker_status_message(
    *,
    connected: bool,
    use_mock: bool,
    connect_note: str,
    pairs: list[OptionPair],
    ticks: dict[str, Tick],
    qmt_error: str = "",
) -> tuple[str, bool]:
    if use_mock:
        sample = pairs[0] if pairs else None
        suffix = (
            f" 平值 {format_code_short(sample.spot_code)} "
            f"K={format_strike_display(sample.strike, sample.spot_code)}"
            if sample and sample.strike > 0
            else ""
        )
        return f"模拟行情（非真实数据），已订阅 {len(collect_quote_codes(pairs))} 个代码。{suffix}", False

    if not connected:
        detail = qmt_error or "QMT未连接"
        return f"获取不到行情：{detail}", False

    missing: list[str] = []
    for code in collect_quote_codes(pairs):
        if ticks.get(code) is None:
            missing.append(format_code_short(code))

    if missing:
        note = f"（{connect_note}）" if connect_note else ""
        return f"QMT已连接{note}，获取不到行情：{', '.join(missing)}", False

    note = f"（{connect_note}）" if connect_note else ""
    return f"QMT已连接{note}，行情正常，已订阅 {len(collect_quote_codes(pairs))} 个代码。", True


def format_market_status_text(status: dict[str, Any]) -> str:
    return format_spot_quotes_text(status) + "\n" + format_contract_targets_text(status)


class QmtQuoteSource:
    def __init__(self, codes: list[str], qmt_path: str = "") -> None:
        self.codes = codes
        self.qmt_path = qmt_path
        self._xtdata: Any = None
        self._ticks: dict[str, Tick] = {}
        self._lock = threading.Lock()
        self.connect_note = ""

    def connect(self) -> None:
        spot_codes = [
            code
            for code in self.codes
            if code and not normalize_market_code(code).endswith((".SHO", ".SZO"))
        ][:6]
        self._xtdata, self.connect_note = connect_xtdata(self.qmt_path, spot_codes or None)
        if hasattr(self._xtdata, "subscribe_whole_quote"):
            try:
                self._xtdata.subscribe_whole_quote(self.codes, self._on_quote)
            except TypeError:
                self._xtdata.subscribe_whole_quote(self.codes, callback=self._on_quote)
            except Exception:
                pass

    def fetch(self) -> dict[str, Tick]:
        if self._xtdata is None:
            return {}
        if hasattr(self._xtdata, "get_full_tick"):
            try:
                raw_ticks = self._xtdata.get_full_tick(self.codes)
                self._merge_raw_ticks(raw_ticks)
            except Exception:
                pass
        with self._lock:
            return dict(self._ticks)

    def _on_quote(self, data: Any) -> None:
        self._merge_raw_ticks(data)

    def _merge_raw_ticks(self, raw_ticks: Any) -> None:
        if not isinstance(raw_ticks, dict):
            return
        parsed: dict[str, Tick] = {}
        for code, raw in raw_ticks.items():
            tick = normalize_tick(raw)
            if tick is not None:
                parsed[str(code)] = tick
        if parsed:
            with self._lock:
                self._ticks.update(parsed)


class MockQuoteSource:
    def __init__(self, pairs: list[OptionPair]) -> None:
        self._prices: dict[str, float] = {}
        for pair in pairs:
            if pair.spot_code not in self._prices:
                base = pair.strike if pair.strike > 0 else 1.0
                self._prices[pair.spot_code] = base * random.uniform(0.985, 1.015)
            self._prices[pair.call_code] = max(
                0.0001,
                abs(self._prices[pair.spot_code] - max(pair.strike, 0.0001)) * 0.4 + 0.015,
            )
            self._prices[pair.put_code] = max(
                0.0001,
                abs(max(pair.strike, 0.0001) - self._prices[pair.spot_code]) * 0.4 + 0.015,
            )

    def fetch(self) -> dict[str, Tick]:
        ticks: dict[str, Tick] = {}
        for code, price in list(self._prices.items()):
            drift = random.uniform(-0.002, 0.002)
            new_price = max(0.0001, price * (1 + drift))
            self._prices[code] = new_price
            spread = max(0.0001, new_price * random.uniform(0.0005, 0.002))
            ticks[code] = Tick(
                bid1=round(max(0.0001, new_price - spread / 2), 4),
                ask1=round(new_price + spread / 2, 4),
                last=round(new_price, 4),
            )
        return ticks


def calculate_opportunities(pairs: list[OptionPair], ticks: dict[str, Tick], fees: FeeConfig) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    now_text = time.strftime("%H:%M:%S")

    for pair in pairs:
        spot = ticks.get(pair.spot_code)
        call = ticks.get(pair.call_code)
        put = ticks.get(pair.put_code)
        if spot is None or call is None or put is None:
            continue

        multiplier = fees.multiplier
        buy_side_option_fees = fees.option_open_fee + fees.option_exercise_fee
        active_exercise_fee = fees.option_exercise_fee
        stock_commission = fees.stock_commission_rate
        strike_cash = pair.strike * multiplier

        spot_mid = quote_mid_price(spot)
        call_mid = quote_mid_price(call)
        put_mid = quote_mid_price(put)

        formulas = [
            {
                "mode_key": "模式1",
                "mode": "模式1 买入认沽 + 买入持有现货",
                "option_code": pair.put_code,
                "is_call": False,
                "is_long_option": True,
                "profit_type": "保底收益",
                "alert_eligible": True,
                "option_bid": put.bid1,
                "option_ask": put.ask1,
                "option_mid": put_mid,
                "profit": strike_cash
                - ((spot.ask1 * multiplier) * (1 + stock_commission) + (put.ask1 * multiplier) + buy_side_option_fees),
                "exercise_upper_profit": None,
                "exercise_condition": "欧式到期结构；到期最差按K形成保底，若到期现货高于K，实际结果可能更好",
                "action": "现货按卖一买入，认沽按卖一买入；主动行权认沽价卖出现货",
            },
            {
                "mode_key": "模式2",
                "mode": "模式2 卖出认沽 + 卖出现货",
                "option_code": pair.put_code,
                "is_call": False,
                "is_long_option": False,
                "profit_type": "条件结构",
                "alert_eligible": False,
                "option_bid": put.bid1,
                "option_ask": put.ask1,
                "option_mid": put_mid,
                "profit": ((spot.bid1 * multiplier) * (1 - stock_commission) + (put.bid1 * multiplier))
                - ((spot.ask1 * multiplier) * (1 + stock_commission)),
                "exercise_upper_profit": ((spot.bid1 * multiplier) * (1 - stock_commission) + (put.bid1 * multiplier))
                - strike_cash,
                "exercise_condition": "卖出认沽开仓不收费，被动接货也不收行权费；主收益按未被行权且按现货卖一回补恢复头寸估算，仅到期<=K且买方最终行权时才接近右侧上限",
                "action": "现货按买一卖出，认沽按买一卖出；被动行权转入期权账户资金等待接货",
            },
            {
                "mode_key": "模式3",
                "mode": "模式3 卖出认购+买入持有现货",
                "option_code": pair.call_code,
                "is_call": True,
                "is_long_option": False,
                "profit_type": "条件结构",
                "alert_eligible": False,
                "option_bid": call.bid1,
                "option_ask": call.ask1,
                "option_mid": call_mid,
                "profit": ((spot.bid1 * multiplier) * (1 - stock_commission) + (call.bid1 * multiplier))
                - ((spot.ask1 * multiplier) * (1 + stock_commission)),
                "exercise_upper_profit": (strike_cash + (call.bid1 * multiplier))
                - ((spot.ask1 * multiplier) * (1 + stock_commission)),
                "exercise_condition": "卖出认购开仓不收费，被动交券也不收行权费；主收益按未被行权且按现货买一卖出落袋估算，仅到期>=K且买方最终行权时才接近右侧上限",
                "action": "持有现货+卖出认购；被动行权提供现货",
            },
            {
                "mode_key": "模式4",
                "mode": "模式4 买入认购 + 卖出现货",
                "option_code": pair.call_code,
                "is_call": True,
                "is_long_option": True,
                "profit_type": "保底收益",
                "alert_eligible": True,
                "option_bid": call.bid1,
                "option_ask": call.ask1,
                "option_mid": call_mid,
                "profit": ((spot.bid1 * multiplier) * (1 - stock_commission))
                - (strike_cash + (call.ask1 * multiplier) + fees.option_open_fee + active_exercise_fee + fees.stock_borrow_cost),
                "exercise_upper_profit": None,
                "exercise_condition": "欧式到期结构；到期最差按K回补，若到期现货低于K，实际结果可能更好",
                "action": "现货按买一卖出，认购按卖一买入；主动行权转入期权账户资金按认购价买入现货",
            },
        ]

        for item in formulas:
            profit = float(item["profit"])
            if profit < fees.min_display_profit:
                continue
            intrinsic, time_value = option_intrinsic_time_value(
                spot_mid,
                pair.strike,
                float(item["option_mid"]),
                is_call=bool(item["is_call"]),
            )
            is_in_the_money = option_is_in_the_money(
                spot_mid,
                pair.strike,
                is_call=bool(item["is_call"]),
            )
            moneyness = option_moneyness_text(spot_mid, pair.strike, is_call=bool(item["is_call"]))
            exercise_status = option_exercise_status_text(
                spot_mid,
                pair.strike,
                is_call=bool(item["is_call"]),
                is_long_option=bool(item["is_long_option"]),
            )
            rows.append(
                {
                    "mode_key": item["mode_key"],
                    "mode": item["mode"],
                    "pool": pair.pool_name,
                    "option_code": item["option_code"],
                    "spot_code": pair.spot_code,
                    "strike": pair.strike,
                    "atm_tier": pair.atm_tier,
                    "tier_label": format_atm_tier_label(pair.atm_tier),
                    "ref_atm_strike": pair.ref_atm_strike,
                    "is_adjusted": pair.is_adjusted,
                    "profit": profit,
                    "profit_type": item["profit_type"],
                    "alert_eligible": bool(item["alert_eligible"]),
                    "is_in_the_money": is_in_the_money,
                    "moneyness_text": moneyness,
                    "exercise_status": exercise_status,
                    "exercise_upper_profit": item.get("exercise_upper_profit"),
                    "spot_bid": spot.bid1,
                    "spot_ask": spot.ask1,
                    "option_bid": item["option_bid"],
                    "option_ask": item["option_ask"],
                    "intrinsic_value": intrinsic,
                    "time_value": time_value,
                    "expiry": pair.expiry,
                    "exercise_condition": item["exercise_condition"],
                    "action": item["action"],
                    "updated_at": now_text,
                    "alert_key": f"{item['mode_key']}|{pair.spot_code}|{item['option_code']}|{pair.strike}",
                }
            )

    rows.sort(key=lambda row: row["profit"], reverse=True)
    return rows


class QuoteWorker(QThread):
    rows_ready = pyqtSignal(list)
    status_ready = pyqtSignal(str, bool)
    market_ready = pyqtSignal(dict)
    diagnostic_ready = pyqtSignal(dict)

    def __init__(self, config_path: Path) -> None:
        super().__init__()
        self.config_path = config_path
        self._running = True
        self._last_alert_at: dict[str, float] = {}
        self._sound_enabled = False
        self._sound_lock = threading.Lock()
        self._sound_generation = 0

    def set_sound_enabled(self, enabled: bool) -> None:
        with self._sound_lock:
            self._sound_enabled = enabled
            if not enabled:
                self._sound_generation += 1
                self._last_alert_at.clear()

    def is_sound_enabled(self) -> bool:
        with self._sound_lock:
            return self._sound_enabled

    def stop(self) -> None:
        self._running = False

    def _emit_connecting(self) -> None:
        self.status_ready.emit("正在连接 QMT...", False)

    def _emit_diagnostic(self, qmt_path: str, connect_note: str = "", qmt_error: str = "") -> None:
        resolved_qmt_path = resolve_qmt_path_for_connect(qmt_path)
        data_dir = qmt_data_dir_from_path(resolved_qmt_path)
        self.diagnostic_ready.emit(
            {
                "config_path": str(self.config_path),
                "configured_qmt_path": qmt_path,
                "resolved_qmt_path": resolved_qmt_path,
                "data_dir": str(data_dir) if data_dir else "",
                "candidate_ports": ordered_qmt_market_ports(resolved_qmt_path),
                "connect_note": connect_note,
                "qmt_error": qmt_error,
            }
        )

    def _emit_qmt_failure(
        self,
        templates: list[OptionPair],
        qmt_error: str,
        *,
        pairs: list[OptionPair] | None = None,
        ticks: dict[str, Tick] | None = None,
    ) -> None:
        display_pairs = pairs if pairs else pairs_from_templates(templates)
        tick_map = ticks if ticks is not None else {}
        error_text = qmt_error or "QMT未连接"
        self.market_ready.emit(
            build_market_status(templates, display_pairs, tick_map, error=error_text)
        )
        self.rows_ready.emit([])
        status_msg, connected = format_worker_status_message(
            connected=False,
            use_mock=False,
            connect_note="",
            pairs=display_pairs,
            ticks=tick_map,
            qmt_error=error_text,
        )
        self.status_ready.emit(status_msg, connected)

    def _try_connect_quote_source(
        self,
        config: dict[str, Any],
        codes: list[str],
        pairs: list[OptionPair],
        templates: list[OptionPair],
        enable_mock: bool,
    ) -> tuple[Any | None, bool, str, str]:
        self._emit_connecting()
        source, use_mock, connect_note, qmt_error = self._create_quote_source(
            config, codes, pairs, enable_mock
        )
        if source is None and not use_mock:
            self._emit_qmt_failure(templates, qmt_error, pairs=pairs_from_templates(templates))
        return source, use_mock, connect_note, qmt_error

    def run(self) -> None:
        try:
            config = load_app_config(self.config_path)
            fees = FeeConfig.from_dict(config["fees"])
            self.set_sound_enabled(fees.sound_enabled)
            qmt_config = config.get("qmt", {})
            qmt_path = str(qmt_config.get("qmt_path", "")).strip()
            self._emit_diagnostic(qmt_path)
            auto_atm = bool(qmt_config.get("auto_atm", True))
            enable_mock = bool(qmt_config.get("enable_mock_when_xtquant_missing", False))
            interval_sec = max(0.05, int(qmt_config.get("poll_interval_ms", 500)) / 1000)
            atm_refresh_sec = max(30.0, float(qmt_config.get("atm_refresh_sec", 300)))
            atm_strike_tiers = max(0, min(5, int(qmt_config.get("atm_strike_tiers", 5))))

            templates = build_option_pairs(config["contract_pools"], auto_atm=auto_atm)
            if not templates:
                self.status_ready.emit("没有可监控的期权合约，请检查配置。", False)
                return

            self._emit_connecting()
            self.market_ready.emit(build_market_status(templates, pairs_from_templates(templates), {}))

            source: Any = None
            use_mock = False
            pairs: list[OptionPair] = []
            subscribed_codes: list[str] = []
            last_atm_refresh = 0.0
            connect_note = ""
            qmt_error = ""

            while self._running:
                now = time.monotonic()
                need_atm_refresh = auto_atm and (not pairs or now - last_atm_refresh >= atm_refresh_sec)

                if not auto_atm and source is None:
                    pairs = resolve_atm_pairs(templates, {}, auto_atm=False, use_mock=False)
                    if not pairs:
                        self.status_ready.emit("没有可监控的期权合约，请检查配置。", False)
                        return
                    subscribed_codes = collect_subscription_codes(templates, pairs)
                    source, use_mock, connect_note, qmt_error = self._try_connect_quote_source(
                        config, subscribed_codes, pairs, templates, enable_mock
                    )
                    self._emit_diagnostic(qmt_path, connect_note, qmt_error)

                if need_atm_refresh:
                    spot_templates = [
                        OptionPair(pool_name=item.pool_name, spot_code=item.spot_code, strike=item.strike, call_code="", put_code="", expiry=item.expiry, name=item.name)
                        for item in templates
                    ]
                    if source is None:
                        initial_codes = collect_subscription_codes(templates)
                        source, use_mock, connect_note, qmt_error = self._try_connect_quote_source(
                            config,
                            initial_codes,
                            templates,
                            templates,
                            enable_mock,
                        )
                        self._emit_diagnostic(qmt_path, connect_note, qmt_error)
                        if source is not None:
                            subscribed_codes = initial_codes

                    refresh_ticks: dict[str, Tick] = source.fetch() if source is not None else {}
                    new_pairs = resolve_atm_pairs(
                        templates,
                        refresh_ticks,
                        auto_atm=True,
                        use_mock=use_mock,
                        max_tiers=atm_strike_tiers,
                    )
                    if not new_pairs:
                        display_pairs = pairs_from_templates(templates)
                        error_text = qmt_error or "无法解析平值期权，请检查QMT期权链与到期日配置"
                        self.market_ready.emit(
                            build_market_status(
                                templates,
                                display_pairs,
                                refresh_ticks,
                                error="" if source is not None and not use_mock else error_text,
                            )
                        )
                        self.rows_ready.emit([])
                        status_msg, connected = format_worker_status_message(
                            connected=source is not None and not use_mock,
                            use_mock=use_mock,
                            connect_note=connect_note,
                            pairs=display_pairs,
                            ticks=refresh_ticks,
                            qmt_error=error_text,
                        )
                        self.status_ready.emit(status_msg, connected)
                        if source is None:
                            source, use_mock, connect_note, qmt_error = self._try_connect_quote_source(
                                config,
                                collect_subscription_codes(templates),
                                templates,
                                templates,
                                enable_mock,
                            )
                            self._emit_diagnostic(qmt_path, connect_note, qmt_error)
                        time.sleep(interval_sec)
                        continue
                    new_codes = collect_subscription_codes(templates, new_pairs)
                    if new_codes != subscribed_codes or source is None:
                        source, use_mock, connect_note, qmt_error = self._try_connect_quote_source(
                            config, new_codes, new_pairs, templates, enable_mock
                        )
                        self._emit_diagnostic(qmt_path, connect_note, qmt_error)
                        subscribed_codes = new_codes
                    pairs = new_pairs
                    last_atm_refresh = now

                if source is None and not auto_atm:
                    display_pairs = pairs if pairs else pairs_from_templates(templates)
                    self._emit_qmt_failure(templates, qmt_error or "QMT未连接", pairs=display_pairs)
                    source, use_mock, connect_note, qmt_error = self._try_connect_quote_source(
                        config,
                        subscribed_codes or collect_subscription_codes(templates, display_pairs),
                        pairs or display_pairs,
                        templates,
                        enable_mock,
                    )
                    self._emit_diagnostic(qmt_path, connect_note, qmt_error)
                    time.sleep(interval_sec)
                    continue

                if source is None or not pairs:
                    display_pairs = pairs if pairs else pairs_from_templates(templates)
                    if source is None:
                        self._emit_qmt_failure(
                            templates,
                            qmt_error or "QMT未连接",
                            pairs=display_pairs,
                        )
                    else:
                        atm_error = qmt_error or "无法解析平值期权，请检查QMT期权链与到期日配置"
                        self.market_ready.emit(
                            build_market_status(templates, display_pairs, {}, error=atm_error)
                        )
                        self.rows_ready.emit([])
                        status_msg, connected = format_worker_status_message(
                            connected=False,
                            use_mock=use_mock,
                            connect_note=connect_note,
                            pairs=display_pairs,
                            ticks={},
                            qmt_error=atm_error,
                        )
                        self.status_ready.emit(status_msg, connected)
                    time.sleep(interval_sec)
                    continue

                try:
                    ticks = source.fetch()
                except Exception as exc:
                    qmt_error = str(exc)
                    self._emit_diagnostic(qmt_path, connect_note, qmt_error)
                    display_pairs = pairs if pairs else pairs_from_templates(templates)
                    self._emit_qmt_failure(
                        templates,
                        f"QMT行情读取失败（{exc}）",
                        pairs=display_pairs,
                    )
                    source = None
                    time.sleep(interval_sec)
                    continue

                self.market_ready.emit(build_market_status(templates, pairs, ticks))
                rows = calculate_opportunities(pairs, ticks, fees)
                status_msg, connected = format_worker_status_message(
                    connected=True,
                    use_mock=use_mock,
                    connect_note=connect_note,
                    pairs=pairs,
                    ticks=ticks,
                    qmt_error=qmt_error,
                )
                self.rows_ready.emit(rows)
                if connected and not use_mock:
                    self._beep_for_alerts(rows, fees)
                self.status_ready.emit(status_msg, connected)
                time.sleep(interval_sec)
        except Exception as exc:
            self.status_ready.emit(f"工作线程异常：{format_qmt_connect_error(exc)}", False)

    def _create_quote_source(
        self,
        config: dict[str, Any],
        codes: list[str],
        pairs: list[OptionPair],
        enable_mock: bool,
    ) -> tuple[Any | None, bool, str, str]:
        try:
            qmt_path = str(config.get("qmt", {}).get("qmt_path", "")).strip()
            source = QmtQuoteSource(codes, qmt_path=qmt_path)
            source.connect()
            return source, False, source.connect_note, ""
        except Exception as exc:
            error_text = format_qmt_connect_error(exc)
            if enable_mock:
                self.status_ready.emit(f"QMT未连接，已启用模拟行情：{error_text}", False)
                return MockQuoteSource(pairs), True, "", error_text
            return None, False, "", error_text

    def _play_alert_beep(self, generation: int, fees: FeeConfig) -> None:
        if not self.is_sound_enabled():
            return
        with self._sound_lock:
            if generation != self._sound_generation:
                return
        try:
            import winsound

            winsound.Beep(fees.alert_frequency_hz, fees.alert_duration_ms)
        except Exception:
            pass

    def _row_quote_is_valid(self, row: dict[str, Any]) -> bool:
        spot_bid = float(row.get("spot_bid", 0))
        spot_ask = float(row.get("spot_ask", 0))
        option_bid = float(row.get("option_bid", 0))
        option_ask = float(row.get("option_ask", 0))
        return spot_bid > 0 and spot_ask > 0 and (option_bid > 0 or option_ask > 0)

    def _beep_for_alerts(self, rows: list[dict[str, Any]], fees: FeeConfig) -> None:
        if not self.is_sound_enabled():
            return
        now = time.monotonic()
        alert_key: str | None = None
        for row in rows:
            if not self.is_sound_enabled():
                return
            if not bool(row.get("alert_eligible")):
                continue
            if float(row["profit"]) < fees.red_threshold:
                continue
            if not self._row_quote_is_valid(row):
                continue
            key = str(row["alert_key"])
            last_at = self._last_alert_at.get(key, 0.0)
            if now - last_at < fees.alert_cooldown_sec:
                continue
            alert_key = key
            break
        if alert_key is None or not self.is_sound_enabled():
            return
        self._last_alert_at[alert_key] = now
        with self._sound_lock:
            generation = self._sound_generation
        threading.Thread(
            target=self._play_alert_beep,
            args=(generation, fees),
            daemon=True,
        ).start()


class ConfigDialog(QDialog):
    CONTRACT_HEADERS = [
        "品种名称",
        "现货代码",
        "合约名称",
        "行权价",
        "认购代码",
        "认沽代码",
        "到期日",
        "启用",
    ]

    def __init__(
        self,
        config: dict[str, Any],
        parent: QWidget | None = None,
        diagnostic_text: str = "",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("配置中心")
        self.resize(1120, 760)
        self._setup_ui()
        self.load_from_config(config)
        self.set_diagnostic_text(diagnostic_text)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        intro = QLabel("在这里直接配置费率、QMT参数、监控合约池和声音报警。保存后会写回配置文件。")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        panel = QWidget(self)
        grid = QGridLayout(panel)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        qmt_box = QGroupBox("QMT 与自动平值", panel)
        qmt_form = QFormLayout(qmt_box)
        self.qmt_path_edit = QLineEdit(qmt_box)
        self.qmt_path_edit.setPlaceholderText(
            "股票期权请填大QMT的 userdata；留空则自动发现。"
            "仅交易端口(58600)无行情，需行情+交易(58670)或 miniQMT(58610)"
        )
        self.poll_interval_spin = QSpinBox(qmt_box)
        self.poll_interval_spin.setRange(50, 10000)
        self.poll_interval_spin.setSuffix(" ms")
        self.auto_atm_checkbox = QCheckBox("根据现价自动选择平值认购/认沽", qmt_box)
        self.enable_mock_checkbox = QCheckBox("QMT未连接时启用模拟行情（默认关闭，不生成假数据）", qmt_box)
        self.atm_refresh_spin = QSpinBox(qmt_box)
        self.atm_refresh_spin.setRange(30, 3600)
        self.atm_refresh_spin.setSuffix(" 秒")
        self.atm_strike_tiers_spin = QSpinBox(qmt_box)
        self.atm_strike_tiers_spin.setRange(0, 5)
        self.atm_strike_tiers_spin.setSuffix(" 档")
        self.atm_strike_tiers_spin.setToolTip("自动平值时向上下扩展的档位数：0=仅平值，5=平值±5档")
        qmt_form.addRow("QMT路径", self.qmt_path_edit)
        qmt_form.addRow("刷新频率", self.poll_interval_spin)
        qmt_form.addRow("平值刷新间隔", self.atm_refresh_spin)
        qmt_form.addRow("平值上下档数", self.atm_strike_tiers_spin)
        qmt_form.addRow("", self.auto_atm_checkbox)
        qmt_form.addRow("", self.enable_mock_checkbox)

        fee_box = QGroupBox("费率与报警", panel)
        fee_form = QFormLayout(fee_box)
        self.multiplier_spin = QSpinBox(fee_box)
        self.multiplier_spin.setRange(1, 1000000)
        self.option_open_fee_spin = self._build_double_spinbox(0, 9999, 4)
        self.option_exercise_fee_spin = self._build_double_spinbox(0, 9999, 4)
        self.stock_commission_rate_spin = self._build_double_spinbox(0, 1, 6)
        self.stock_borrow_cost_spin = self._build_double_spinbox(0, 999999, 4)
        self.yellow_threshold_spin = self._build_double_spinbox(0, 999999, 2)
        self.red_threshold_spin = self._build_double_spinbox(0, 999999, 2)
        self.alert_frequency_spin = QSpinBox(fee_box)
        self.alert_frequency_spin.setRange(100, 10000)
        self.alert_duration_spin = QSpinBox(fee_box)
        self.alert_duration_spin.setRange(50, 5000)
        self.alert_duration_spin.setSuffix(" ms")
        self.alert_cooldown_spin = self._build_double_spinbox(0, 600, 2)
        self.min_display_profit_spin = self._build_double_spinbox(-999999, 999999, 2)
        self.sound_enabled_checkbox = QCheckBox("启用声音报警", fee_box)
        fee_form.addRow("合约乘数", self.multiplier_spin)
        fee_form.addRow("期权买入开仓费", self.option_open_fee_spin)
        fee_form.addRow("主动行权费", self.option_exercise_fee_spin)
        fee_form.addRow("现货佣金率", self.stock_commission_rate_spin)
        fee_form.addRow("融券利息成本", self.stock_borrow_cost_spin)
        fee_form.addRow("黄色高亮阈值", self.yellow_threshold_spin)
        fee_form.addRow("红色高亮/报警阈值", self.red_threshold_spin)
        fee_form.addRow("报警频率", self.alert_frequency_spin)
        fee_form.addRow("报警时长", self.alert_duration_spin)
        fee_form.addRow("报警冷却时间", self.alert_cooldown_spin)
        fee_form.addRow("最小显示利润", self.min_display_profit_spin)
        fee_form.addRow("", self.sound_enabled_checkbox)

        grid.addWidget(qmt_box, 0, 0)
        grid.addWidget(fee_box, 0, 1)
        layout.addWidget(panel)

        contract_bar = QHBoxLayout()
        contract_bar.addWidget(QLabel("监控合约池"))
        contract_bar.addStretch(1)
        self.reset_contract_button = QPushButton("恢复示例合约")
        self.remove_contract_button = QPushButton("删除选中行")
        self.add_contract_button = QPushButton("新增合约")
        self.reset_contract_button.clicked.connect(self.reset_contract_rows)
        self.remove_contract_button.clicked.connect(self.remove_selected_contract_rows)
        self.add_contract_button.clicked.connect(self.add_contract_row)
        contract_bar.addWidget(self.reset_contract_button)
        contract_bar.addWidget(self.remove_contract_button)
        contract_bar.addWidget(self.add_contract_button)
        layout.addLayout(contract_bar)

        self.contract_table = QTableWidget(0, len(self.CONTRACT_HEADERS), self)
        self.contract_table.setHorizontalHeaderLabels(self.CONTRACT_HEADERS)
        self.contract_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.contract_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.contract_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.contract_table.verticalHeader().setVisible(False)
        layout.addWidget(self.contract_table, stretch=1)

        help_text = QLabel(
            "每一行代表一个监控的认购/认沽配对。勾选自动平值后，认购/认沽代码可以留空。"
            "默认不启用模拟行情；QMT 未连接或取不到盘口时，界面会显示“获取不到行情”，不会伪造数据。"
        )
        help_text.setWordWrap(True)
        layout.addWidget(help_text)

        diagnostic_box = QGroupBox("连接诊断", self)
        diagnostic_layout = QVBoxLayout(diagnostic_box)
        diagnostic_hint = QLabel("首页只保留简洁状态，详细的 QMT 路径、data_dir、端口和错误信息放在这里查看。")
        diagnostic_hint.setWordWrap(True)
        diagnostic_layout.addWidget(diagnostic_hint)
        self.diagnostic_text_edit = QTextEdit(diagnostic_box)
        self.diagnostic_text_edit.setReadOnly(True)
        self.diagnostic_text_edit.setMinimumHeight(120)
        self.diagnostic_text_edit.setMaximumHeight(180)
        diagnostic_layout.addWidget(self.diagnostic_text_edit)
        diagnostic_actions = QHBoxLayout()
        diagnostic_actions.addStretch(1)
        self.copy_diagnostic_button = QPushButton("复制诊断", diagnostic_box)
        self.copy_diagnostic_button.clicked.connect(self.copy_diagnostic_text)
        diagnostic_actions.addWidget(self.copy_diagnostic_button)
        diagnostic_layout.addLayout(diagnostic_actions)
        layout.addWidget(diagnostic_box)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _build_double_spinbox(self, minimum: float, maximum: float, decimals: int) -> QDoubleSpinBox:
        spin = QDoubleSpinBox(self)
        spin.setRange(minimum, maximum)
        spin.setDecimals(decimals)
        spin.setSingleStep(10 ** (-decimals) if decimals > 0 else 1)
        return spin

    def set_diagnostic_text(self, text: str) -> None:
        diagnostic = str(text or "").strip() or "暂无诊断信息"
        self.diagnostic_text_edit.setPlainText(diagnostic)

    def copy_diagnostic_text(self) -> None:
        QApplication.clipboard().setText(self.diagnostic_text_edit.toPlainText())
        QMessageBox.information(self, "已复制", "连接诊断信息已复制到剪贴板。")

    def load_from_config(self, config: dict[str, Any]) -> None:
        qmt = config.get("qmt", {})
        fees = config.get("fees", {})
        self.qmt_path_edit.setText(str(qmt.get("qmt_path", "")))
        self.poll_interval_spin.setValue(int(qmt.get("poll_interval_ms", 500)))
        self.auto_atm_checkbox.setChecked(bool(qmt.get("auto_atm", True)))
        self.enable_mock_checkbox.setChecked(bool(qmt.get("enable_mock_when_xtquant_missing", False)))
        self.atm_refresh_spin.setValue(int(qmt.get("atm_refresh_sec", 300)))
        self.atm_strike_tiers_spin.setValue(int(qmt.get("atm_strike_tiers", 5)))

        self.multiplier_spin.setValue(int(fees.get("multiplier", 10000)))
        self.option_open_fee_spin.setValue(float(fees.get("option_open_fee", 1.7)))
        self.option_exercise_fee_spin.setValue(float(fees.get("option_exercise_fee", 4.0)))
        self.stock_commission_rate_spin.setValue(float(fees.get("stock_commission_rate", 0.0001)))
        self.stock_borrow_cost_spin.setValue(float(fees.get("stock_borrow_cost", 0.0)))
        self.yellow_threshold_spin.setValue(float(fees.get("yellow_threshold", 20.0)))
        self.red_threshold_spin.setValue(float(fees.get("red_threshold", 50.0)))
        self.alert_frequency_spin.setValue(int(fees.get("alert_frequency_hz", 1200)))
        self.alert_duration_spin.setValue(int(fees.get("alert_duration_ms", 250)))
        self.alert_cooldown_spin.setValue(float(fees.get("alert_cooldown_sec", 3.0)))
        self.min_display_profit_spin.setValue(float(fees.get("min_display_profit", -999999.0)))
        self.sound_enabled_checkbox.setChecked(bool(fees.get("sound_enabled", True)))

        self.contract_table.setRowCount(0)
        for pool in config.get("contract_pools", []):
            for option in pool.get("options", []):
                self.add_contract_row(
                    {
                        "pool_name": pool.get("name", ""),
                        "spot_code": pool.get("spot_code", ""),
                        "name": option.get("name", ""),
                        "strike": option.get("strike", 0),
                        "call_code": option.get("call_code", ""),
                        "put_code": option.get("put_code", ""),
                        "expiry": option.get("expiry", ""),
                        "enabled": option.get("enabled", True),
                    }
                )
        if self.contract_table.rowCount() == 0:
            self.reset_contract_rows()

    def add_contract_row(self, row_data: dict[str, Any] | None = None) -> None:
        defaults = row_data or {
            "pool_name": "50ETF",
            "spot_code": "510050.SH",
            "name": "",
            "strike": 0.0,
            "call_code": "",
            "put_code": "",
            "expiry": "",
            "enabled": True,
        }
        row = self.contract_table.rowCount()
        self.contract_table.insertRow(row)
        values = [
            str(defaults["pool_name"]),
            str(defaults["spot_code"]),
            str(defaults["name"]),
            str(defaults["strike"]),
            str(defaults["call_code"]),
            str(defaults["put_code"]),
            str(defaults["expiry"]),
        ]
        for column, value in enumerate(values):
            self.contract_table.setItem(row, column, QTableWidgetItem(value))

        enabled_item = QTableWidgetItem("")
        enabled_item.setFlags(
            Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsUserCheckable
        )
        enabled_item.setCheckState(
            Qt.CheckState.Checked if bool(defaults["enabled"]) else Qt.CheckState.Unchecked
        )
        self.contract_table.setItem(row, 7, enabled_item)

    def remove_selected_contract_rows(self) -> None:
        rows = sorted({item.row() for item in self.contract_table.selectedItems()}, reverse=True)
        for row in rows:
            self.contract_table.removeRow(row)

    def reset_contract_rows(self) -> None:
        self.contract_table.setRowCount(0)
        for pool in default_contract_pools():
            for option in pool["options"]:
                self.add_contract_row(
                    {
                        "pool_name": pool["name"],
                        "spot_code": pool["spot_code"],
                        "name": option["name"],
                        "strike": option["strike"],
                        "call_code": option["call_code"],
                        "put_code": option["put_code"],
                        "expiry": option["expiry"],
                        "enabled": option["enabled"],
                    }
                )

    def _text(self, row: int, column: int) -> str:
        item = self.contract_table.item(row, column)
        return item.text().strip() if item else ""

    def _checked(self, row: int, column: int) -> bool:
        item = self.contract_table.item(row, column)
        return bool(item and item.checkState() == Qt.CheckState.Checked)

    def to_config(self) -> dict[str, Any]:
        contract_pools_by_key: dict[tuple[str, str], dict[str, Any]] = {}
        auto_atm = self.auto_atm_checkbox.isChecked()

        for row in range(self.contract_table.rowCount()):
            pool_name = self._text(row, 0)
            spot_code = self._text(row, 1)
            option_name = self._text(row, 2)
            strike_text = self._text(row, 3)
            call_code = self._text(row, 4)
            put_code = self._text(row, 5)
            expiry = self._text(row, 6)
            enabled = self._checked(row, 7)

            if not pool_name and not spot_code and not call_code and not put_code:
                continue
            if not pool_name:
                raise ValueError(f"第 {row + 1} 行缺少品种名称。")
            if not spot_code:
                raise ValueError(f"第 {row + 1} 行缺少现货代码。")
            if not auto_atm and not call_code:
                raise ValueError(f"第 {row + 1} 行缺少认购代码。")
            if not auto_atm and not put_code:
                raise ValueError(f"第 {row + 1} 行缺少认沽代码。")

            if strike_text:
                try:
                    strike = float(strike_text)
                except ValueError as exc:
                    raise ValueError(f"第 {row + 1} 行的行权价格式不正确。") from exc
            else:
                strike = 0.0

            key = (pool_name, spot_code)
            pool = contract_pools_by_key.setdefault(
                key,
                {"name": pool_name, "spot_code": spot_code, "options": []},
            )
            pool["options"].append(
                {
                    "name": option_name,
                    "strike": strike,
                    "call_code": call_code,
                    "put_code": put_code,
                    "expiry": expiry,
                    "enabled": enabled,
                }
            )

        contract_pools = list(contract_pools_by_key.values())
        if not contract_pools:
            raise ValueError("请至少保留一组监控合约。")

        return {
            "qmt": {
                "qmt_path": self.qmt_path_edit.text().strip(),
                "poll_interval_ms": int(self.poll_interval_spin.value()),
                "enable_mock_when_xtquant_missing": self.enable_mock_checkbox.isChecked(),
                "auto_atm": self.auto_atm_checkbox.isChecked(),
                "atm_refresh_sec": int(self.atm_refresh_spin.value()),
                "atm_strike_tiers": int(self.atm_strike_tiers_spin.value()),
            },
            "fees": {
                "multiplier": int(self.multiplier_spin.value()),
                "option_open_fee": float(self.option_open_fee_spin.value()),
                "option_exercise_fee": float(self.option_exercise_fee_spin.value()),
                "stock_commission_rate": float(self.stock_commission_rate_spin.value()),
                "stock_borrow_cost": float(self.stock_borrow_cost_spin.value()),
                "yellow_threshold": float(self.yellow_threshold_spin.value()),
                "red_threshold": float(self.red_threshold_spin.value()),
                "alert_frequency_hz": int(self.alert_frequency_spin.value()),
                "alert_duration_ms": int(self.alert_duration_spin.value()),
                "alert_cooldown_sec": float(self.alert_cooldown_spin.value()),
                "min_display_profit": float(self.min_display_profit_spin.value()),
                "sound_enabled": self.sound_enabled_checkbox.isChecked(),
            },
            "contract_pools": contract_pools,
        }

    def accept(self) -> None:
        try:
            self.to_config()
        except ValueError as exc:
            QMessageBox.warning(self, "配置有误", str(exc))
            return
        super().accept()


class MainWindow(QMainWindow):
    MODE_TABLE_HEADERS = [
        "品种",
        "期权代码",
        "行权价",
        "档位",
        "未被行权每张收益(元)",
        "若被行权上限",
        "收益类型",
        "当前状态",
        "当前行权判断",
        "现货买一",
        "现货卖一",
        "期权买一",
        "期权卖一",
        "内在价值",
        "时间价值",
        "到期日",
        "更新时间",
        "实现条件",
        "操作参考盘口说明",
    ]
    _NUMERIC_TABLE_COLUMNS = {2, 4, 5, 9, 10, 11, 12, 13, 14}
    _PROFIT_COLUMN = 4
    _UPPER_PROFIT_COLUMN = 5
    _EXERCISE_STATUS_COLUMN = 8
    _TIME_VALUE_COLUMN = 14
    _QUOTE_COLUMN_GROUP_STYLES = {
        9: ("#dbeafe", "#eff6ff", "#0c4a6e"),
        10: ("#dbeafe", "#eff6ff", "#0c4a6e"),
        11: ("#ede9fe", "#f5f3ff", "#5b21b6"),
        12: ("#ede9fe", "#f5f3ff", "#5b21b6"),
        13: ("#fef3c7", "#fffbeb", "#92400e"),
        14: ("#fef3c7", "#fffbeb", "#92400e"),
    }

    def __init__(self, config_path: Path) -> None:
        super().__init__()
        self.config_path = config_path
        self.config = load_app_config(config_path)
        self.fees = FeeConfig.from_dict(self.config["fees"])
        self.is_frozen = False
        self.latest_rows: list[dict[str, Any]] = []
        self.latest_diagnostic_info: dict[str, Any] = {}
        self.config_dialog: ConfigDialog | None = None
        self.rendered_rows_by_mode: dict[str, list[dict[str, Any]]] = {
            mode_key: [] for mode_key, _, _ in ARBITRAGE_MODE_DEFS
        }
        self.mode_tables: dict[str, QTableWidget] = {}
        self.mode_boxes: dict[str, QGroupBox] = {}
        self.mode_base_titles: dict[str, str] = {}
        self.tier_checkboxes: dict[int, QCheckBox] = {}
        self.pool_checkboxes: dict[str, QCheckBox] = {}
        self.pool_filter_layout: QHBoxLayout | None = None
        self.tier_filter_layout: QHBoxLayout | None = None

        self.setWindowTitle(APP_WINDOW_TITLE)
        self.resize(1680, 980)
        self._setup_ui()
        self._start_worker()

    def _setup_ui(self) -> None:
        root = QWidget(self)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)
        self.sound_checkbox = QCheckBox("声音")
        self.sound_checkbox.setStyleSheet("font-size:11px;")
        self.sound_checkbox.setChecked(self.fees.sound_enabled)
        self.sound_checkbox.toggled.connect(self.on_sound_toggled)
        self.config_button = QPushButton("配置")
        self.config_button.clicked.connect(self.open_config_dialog)
        self.formula_button = QPushButton("公式")
        self.formula_button.clicked.connect(self.show_formula_explanation)
        self.post_market_button = QPushButton("盘后计算")
        self.post_market_button.clicked.connect(self.open_post_market_ledger)
        self.reload_button = QPushButton("重载")
        self.reload_button.clicked.connect(self.reload_config)
        self.freeze_button = QPushButton("锁定")
        self.freeze_button.clicked.connect(self.toggle_freeze)
        for button in (
            self.config_button,
            self.formula_button,
            self.post_market_button,
            self.reload_button,
            self.freeze_button,
        ):
            button.setFixedHeight(24)
            button.setStyleSheet("font-size:11px; padding:0 8px;")
        toolbar.addWidget(self.sound_checkbox)
        toolbar.addWidget(self.config_button)
        toolbar.addWidget(self.formula_button)
        toolbar.addWidget(self.post_market_button)
        toolbar.addWidget(self.reload_button)
        toolbar.addWidget(self.freeze_button)

        market_caption = QLabel("现货行情")
        market_caption.setStyleSheet("font-weight: 600; color: #333333; font-size: 11px;")
        self.status_label = QLabel("QMT 正在连接…")
        self.status_label.setStyleSheet("font-weight: 600; color: #8a6d00; font-size: 10px;")
        self.status_label.setWordWrap(False)
        self.status_label.setMaximumWidth(280)
        self.status_label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        self.spot_chips_widget = QWidget(self)
        self.spot_chips_widget.setFixedHeight(18)
        self.spot_quote_layout = QHBoxLayout(self.spot_chips_widget)
        self.spot_quote_layout.setContentsMargins(0, 0, 0, 0)
        self.spot_quote_layout.setSpacing(2)
        spot_scroll = QScrollArea(self)
        spot_scroll.setWidget(self.spot_chips_widget)
        spot_scroll.setWidgetResizable(True)
        spot_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        spot_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        spot_scroll.setFixedHeight(20)
        spot_scroll.setFrameShape(QFrame.Shape.NoFrame)
        spot_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        toolbar.addWidget(market_caption)
        toolbar.addWidget(self.status_label)
        toolbar.addWidget(spot_scroll, stretch=1)
        layout.addLayout(toolbar)

        self.error_banner = QLabel("")
        self.error_banner.setWordWrap(True)
        self.error_banner.setVisible(False)
        self.error_banner.setStyleSheet(
            "background:#fff3e0; color:#e65100; padding:4px 8px; border-radius:4px;"
            "border:1px solid #ffcc80; font-size:11px;"
        )
        layout.addWidget(self.error_banner)

        contract_box = QGroupBox(self)
        contract_box.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        contract_layout = QVBoxLayout(contract_box)
        contract_layout.setContentsMargins(6, 4, 6, 6)
        contract_layout.setSpacing(4)
        contract_head = QHBoxLayout()
        contract_head.setContentsMargins(0, 0, 0, 0)
        contract_caption = QLabel("当前平值合约")
        contract_caption.setStyleSheet("font-weight: 600; color: #333333;")
        self.option_summary_label = QLabel("期权盘口：等待连接")
        self.option_summary_label.setStyleSheet("color:#555555; font-size:12px;")
        contract_head.addWidget(contract_caption)
        contract_head.addWidget(self.option_summary_label)
        contract_head.addStretch(1)
        contract_layout.addLayout(contract_head)
        self.contract_table = QTableWidget(0, len(CONTRACT_TABLE_HEADERS), self)
        self.contract_table.setHorizontalHeaderLabels(CONTRACT_TABLE_HEADERS)
        self.contract_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.contract_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.contract_table.setAlternatingRowColors(True)
        self.contract_table.verticalHeader().setVisible(False)
        self.contract_table.setShowGrid(True)
        self.contract_table.horizontalHeader().setStretchLastSection(True)
        self.contract_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.contract_table.setStyleSheet(
            "QTableWidget { font-size: 11px; }"
            "QHeaderView::section { font-size: 10px; padding: 2px 4px; }"
        )
        self.contract_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.contract_table.setMinimumHeight(88)
        self.contract_table.setMaximumHeight(156)
        contract_layout.addWidget(self.contract_table)
        layout.addWidget(contract_box)

        recommend_box = QGroupBox("推荐操作", self)
        recommend_layout = QVBoxLayout(recommend_box)
        self.recommendation_label = QLabel("推荐1-3：等待行情与收益计算，默认优先展示保底收益机会。")
        self.recommendation_label.setWordWrap(True)
        self.recommendation_label.setStyleSheet(
            "background:#f6fbf7; color:#1f3b2d; padding:6px 8px; border-radius:4px;"
            "border:1px solid #cfe8d6; font-size:12px;"
        )
        recommend_layout.addWidget(self.recommendation_label)
        self.recommendation_guidance_label = QLabel(
            "交易提示：等待行情与收益计算后显示时间价值和主动行权提醒。"
        )
        self.recommendation_guidance_label.setTextFormat(Qt.TextFormat.RichText)
        self.recommendation_guidance_label.setWordWrap(True)
        self.recommendation_guidance_label.setStyleSheet(
            "background:#eef6ff; color:#174a72; padding:5px 8px; border-radius:4px;"
            "border:1px solid #c9def2; font-size:11px;"
        )
        recommend_layout.addWidget(self.recommendation_guidance_label)
        layout.addWidget(recommend_box)

        filtered_recommend_box = QGroupBox("当前筛选推荐", self)
        filtered_recommend_layout = QVBoxLayout(filtered_recommend_box)
        self.filtered_recommendation_label = QLabel("等待下方品种筛选与行情联动。")
        self.filtered_recommendation_label.setWordWrap(True)
        self.filtered_recommendation_label.setStyleSheet(
            "background:#fffaf0; color:#5f370e; padding:6px 8px; border-radius:4px;"
            "border:1px solid #f3d7a3; font-size:12px;"
        )
        filtered_recommend_layout.addWidget(self.filtered_recommendation_label)
        layout.addWidget(filtered_recommend_box)

        filter_box = QGroupBox("表格筛选", self)
        filter_row = QHBoxLayout(filter_box)
        filter_row.setSpacing(6)
        filter_row.setContentsMargins(6, 2, 6, 6)
        tier_caption = QLabel("档位")
        tier_caption.setStyleSheet("color:#666; font-size:10px;")
        filter_row.addWidget(tier_caption)
        tier_row_widget = QWidget(self)
        self.tier_filter_layout = QHBoxLayout(tier_row_widget)
        self.tier_filter_layout.setContentsMargins(0, 0, 0, 0)
        self.tier_filter_layout.setSpacing(4)
        for tier in range(6):
            checkbox = QCheckBox(format_atm_tier_label(tier), self)
            checkbox.setStyleSheet(COMPACT_CHECKBOX_STYLE)
            checkbox.setChecked(tier <= 1)
            checkbox.toggled.connect(self.on_tier_filter_changed)
            self.tier_checkboxes[tier] = checkbox
            self.tier_filter_layout.addWidget(checkbox)
        self.hide_adjusted_checkbox = QCheckBox("隐藏 A 合约", self)
        self.hide_adjusted_checkbox.setStyleSheet(COMPACT_CHECKBOX_STYLE)
        self.hide_adjusted_checkbox.setChecked(True)
        self.hide_adjusted_checkbox.setToolTip(
            "隐藏交易所调整过的期权合约（合约名称含「调整」或行权价后缀 A，如 5604A）"
        )
        self.hide_adjusted_checkbox.toggled.connect(self.on_display_filter_changed)
        self.tier_filter_layout.addWidget(self.hide_adjusted_checkbox)
        filter_row.addWidget(tier_row_widget)

        pool_caption = QLabel("品种")
        pool_caption.setStyleSheet("color:#666; font-size:10px;")
        filter_row.addWidget(pool_caption)
        pool_row_widget = QWidget(self)
        pool_row_widget.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.pool_filter_layout = QHBoxLayout(pool_row_widget)
        self.pool_filter_layout.setContentsMargins(0, 0, 0, 0)
        self.pool_filter_layout.setSpacing(4)
        filter_row.addWidget(pool_row_widget)
        filter_row.addStretch(1)
        self._rebuild_pool_filter_widgets()
        layout.addWidget(filter_box)

        mode_grid = QGridLayout()
        mode_grid.setHorizontalSpacing(10)
        mode_grid.setVerticalSpacing(10)
        for index, (mode_key, panel_title, mode_hint) in enumerate(ARBITRAGE_MODE_DEFS):
            row = index // 2
            column = index % 2
            base_title = f"{panel_title}（{mode_hint}）"
            self.mode_base_titles[mode_key] = base_title
            box = QGroupBox(f"{base_title} · 0条", self)
            box_layout = QVBoxLayout(box)
            box_layout.setContentsMargins(8, 8, 8, 8)
            box_layout.setSpacing(6)

            time_value_requirement = QLabel(MODE_TIME_VALUE_REQUIREMENTS[mode_key], box)
            time_value_requirement.setStyleSheet(
                "color:#d90429; font-weight:600; font-size:11px; padding:0 2px;"
            )
            box_layout.addWidget(time_value_requirement)

            table = QTableWidget(0, len(self.MODE_TABLE_HEADERS), box)
            table.setHorizontalHeaderLabels(self.MODE_TABLE_HEADERS)
            for header_column in range(len(self.MODE_TABLE_HEADERS)):
                header_item = table.horizontalHeaderItem(header_column)
                if header_item is not None:
                    self._apply_quote_column_group_style(header_item, header_column, is_header=True)
            table.setAlternatingRowColors(True)
            table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            table.horizontalHeader().setStretchLastSection(True)
            table.verticalHeader().setVisible(False)
            table.cellDoubleClicked.connect(lambda _row, _column: self.toggle_freeze())
            box_layout.addWidget(table, stretch=1)

            self.mode_tables[mode_key] = table
            self.mode_boxes[mode_key] = box
            mode_grid.addWidget(box, row, column)

        layout.addLayout(mode_grid, stretch=1)

        self.summary_label = QLabel(
            "四个模式已在首页同时展示。双击任意表格行可以冻结/恢复画面，右上角可直接关闭声音报警。"
        )
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        self.setCentralWidget(root)

    def _set_mode_box_count(self, mode_key: str, count: int) -> None:
        base_title = self.mode_base_titles.get(mode_key)
        box = self.mode_boxes.get(mode_key)
        if base_title and box is not None:
            box.setTitle(f"{base_title} · {count}条")

    def _configured_pool_names(self) -> list[str]:
        names: list[str] = []
        for pool in self.config.get("contract_pools", []):
            name = str(pool.get("name", "")).strip()
            if name and name not in names:
                names.append(name)
        if names:
            return names
        return ["50ETF", "588000ETF", "300ETF", "500ETF", "159915"]

    def _rebuild_pool_filter_widgets(self) -> None:
        if self.pool_filter_layout is None:
            return
        previous_checked = {
            name: checkbox.isChecked() for name, checkbox in self.pool_checkboxes.items()
        }
        if self.pool_filter_layout is None:
            return
        self._clear_layout(self.pool_filter_layout)
        self.pool_checkboxes.clear()

        for pool_name in self._configured_pool_names():
            checkbox = QCheckBox(pool_name, self)
            checkbox.setStyleSheet(COMPACT_CHECKBOX_STYLE)
            checkbox.setChecked(
                previous_checked.get(pool_name, pool_name in DEFAULT_UI_POOL_FILTER_NAMES)
            )
            checkbox.toggled.connect(self.on_display_filter_changed)
            self.pool_checkboxes[pool_name] = checkbox
            self.pool_filter_layout.addWidget(checkbox)
        if self.latest_rows and not self.is_frozen:
            self.render_rows(self.latest_rows)
            self._update_recommendations(self.latest_rows)

    def _selected_pool_names(self) -> set[str]:
        return {name for name, checkbox in self.pool_checkboxes.items() if checkbox.isChecked()}

    def _start_worker(self) -> None:
        self.worker = QuoteWorker(self.config_path)
        self.worker.rows_ready.connect(self.on_rows_ready)
        self.worker.status_ready.connect(self.on_status_ready)
        self.worker.market_ready.connect(self.on_market_ready)
        self.worker.diagnostic_ready.connect(self.on_diagnostic_ready)
        self.worker.start()

    def _restart_worker(self) -> None:
        if hasattr(self, "worker"):
            self.worker.stop()
            self.worker.wait(2000)
        self.latest_rows = []
        self.rendered_rows_by_mode = {
            mode_key: [] for mode_key, _, _ in ARBITRAGE_MODE_DEFS
        }
        for mode_key, table in self.mode_tables.items():
            table.setRowCount(0)
            self._set_mode_box_count(mode_key, 0)
        self._update_market_panel({"spots": {}, "contracts": {}, "option_total": 0, "option_ok": 0, "error": ""})
        self._sync_contract_table_height()
        self.recommendation_label.setText("推荐1-3：等待行情与收益计算，默认优先展示保底收益机会。")
        self.recommendation_guidance_label.setText(
            "交易提示：等待行情与收益计算后显示时间价值和主动行权提醒。"
        )
        self.filtered_recommendation_label.setText("等待下方品种筛选与行情联动。")
        self.on_status_ready("正在重新连接 QMT...", False)
        self._start_worker()

    @staticmethod
    def _clear_layout(layout: QHBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _update_market_panel(self, status: dict[str, Any]) -> None:
        error = str(status.get("error") or "").strip()
        show_banner = bool(error) and not is_market_connection_error(error)
        self.error_banner.setVisible(show_banner)
        if show_banner:
            self.error_banner.setText(f"行情提示：{error}")

        self._clear_layout(self.spot_quote_layout)
        spots = status.get("spots", {})
        if not spots:
            placeholder = QLabel("—")
            placeholder.setStyleSheet("color:#888888; font-size:11px;")
            self.spot_quote_layout.addWidget(placeholder)
        else:
            for code in sorted(spots):
                quote = spots[code]
                short_code = format_code_short(code)
                if quote.get("ok"):
                    text = f"{short_code} {quote['bid']:.3f}/{quote['ask']:.3f}"
                    style = SPOT_CHIP_STYLE_OK
                else:
                    text = f"{short_code}—"
                    style = SPOT_CHIP_STYLE_BAD
                chip = QLabel(text)
                chip.setStyleSheet(style)
                chip.setFixedHeight(18)
                chip.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
                self.spot_quote_layout.addWidget(chip)

        option_total = int(status.get("option_total", 0))
        option_ok = int(status.get("option_ok", 0))
        if option_total:
            self.option_summary_label.setText(f"期权盘口：{option_ok} / {option_total} 有效")
        else:
            self.option_summary_label.setText("期权盘口：等待解析认购/认沽")

        contracts = status.get("contracts", {})
        self.contract_table.setRowCount(len(contracts))
        for row_index, spot_code in enumerate(sorted(contracts)):
            info = contracts[spot_code]
            short_code = format_code_short(spot_code)
            pool = str(info.get("pool") or short_code)
            strike = first_number(info.get("strike"))
            strike_text = format_strike_display(strike, spot_code) if strike > 0 else "-"
            call_code = str(info.get("call") or "-")
            put_code = str(info.get("put") or "-")
            expiry = str(info.get("expiry") or "-")
            spot_quote = status.get("spots", {}).get(spot_code, {})
            spot_price = first_number(spot_quote.get("price"))
            spot_price_text = f"{spot_price:.4f}" if spot_price > 0 else "无行情"
            if info.get("atm_pending"):
                call_status = str(info.get("chain_error") or "待自动平值")
                put_status = ""
            else:
                call_status = _quote_status_text(bool(info.get("call_ok")))
                put_status = _quote_status_text(bool(info.get("put_ok")))

            values = [
                pool,
                short_code,
                spot_price_text,
                strike_text,
                expiry,
                call_code,
                put_code,
                call_status,
                put_status,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column in {2, 3}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if column == 7 and not info.get("atm_pending"):
                    _apply_table_status_item(item, bool(info.get("call_ok")))
                if column == 8 and not info.get("atm_pending"):
                    _apply_table_status_item(item, bool(info.get("put_ok")))
                if column == 1 and not spot_quote.get("ok"):
                    item.setForeground(QColor("#c62828"))
                self.contract_table.setItem(row_index, column, item)
        self.contract_table.resizeColumnsToContents()
        self._sync_contract_table_height()

    def _sync_contract_table_height(self) -> None:
        row_count = max(1, self.contract_table.rowCount())
        visible_rows = min(row_count, 6)
        header_height = self.contract_table.horizontalHeader().height()
        row_height = self.contract_table.verticalHeader().defaultSectionSize()
        frame_height = self.contract_table.frameWidth() * 2
        table_height = header_height + (visible_rows * row_height) + frame_height + 6
        self.contract_table.setFixedHeight(max(88, min(156, table_height)))

    @staticmethod
    def _format_qmt_status_display(message: str) -> str:
        text = str(message or "").strip()
        if not text:
            return "QMT"
        if text.startswith("QMT"):
            compact = text
        elif "正在重新连接" in text and "QMT" in text:
            compact = "QMT 正在重新连接"
        elif "正在连接" in text and "QMT" in text:
            compact = "QMT 正在连接"
        else:
            compact = f"QMT · {text}"
        return compact.replace("，行情正常", "")

    def on_status_ready(self, message: str, connected: bool) -> None:
        display = self._format_qmt_status_display(message)
        if display:
            display = f"{display}，{time.strftime('%H:%M:%S')}"
        self.status_label.setToolTip(display)
        if display:
            max_width = max(120, self.status_label.maximumWidth())
            display = self.status_label.fontMetrics().elidedText(
                display,
                Qt.TextElideMode.ElideRight,
                max_width,
            )
        self.status_label.setText(display)
        if connected:
            self.status_label.setStyleSheet("font-weight: 600; color: #0b7a3b; font-size: 10px;")
        else:
            self.status_label.setStyleSheet("font-weight: 600; color: #b54708; font-size: 10px;")
            if not is_market_connection_error(message):
                self.error_banner.setVisible(True)
                self.error_banner.setText(f"状态：{message}")
            else:
                self.error_banner.setVisible(False)

    def on_market_ready(self, status: dict[str, Any]) -> None:
        self._update_market_panel(status)

    def on_diagnostic_ready(self, info: dict[str, Any]) -> None:
        self.latest_diagnostic_info = dict(info)
        if self.config_dialog is not None:
            self.config_dialog.set_diagnostic_text(self._format_diagnostic_text(info))

    def _format_diagnostic_text(self, info: dict[str, Any]) -> str:
        ports = ",".join(str(port) for port in info.get("candidate_ports", []))
        lines = [
            f"配置文件: {info.get('config_path', '')}",
            f"配置QMT路径: {info.get('configured_qmt_path', '') or '-'}",
            f"实际QMT路径: {info.get('resolved_qmt_path', '') or '-'}",
            f"data_dir: {info.get('data_dir', '') or '-'}",
            f"候选端口: {ports or '-'}",
        ]
        connect_note = str(info.get("connect_note") or "").strip()
        qmt_error = str(info.get("qmt_error") or "").strip()
        if connect_note:
            lines.append(f"连接说明: {connect_note}")
        if qmt_error:
            lines.append(f"错误信息: {qmt_error}")
        return "\n".join(lines)

    def on_rows_ready(self, rows: list[dict[str, Any]]) -> None:
        self.latest_rows = rows
        if not self.is_frozen:
            self.render_rows(rows)
        self._update_recommendations(rows)
        mode_counts = " | ".join(
            f"{mode_key} {len(self.rendered_rows_by_mode.get(mode_key, []))}条"
            for mode_key, _, _ in ARBITRAGE_MODE_DEFS
        )
        sound_text = "开启" if self.fees.sound_enabled else "关闭"
        self.summary_label.setText(
            f"最新扫描共 {len(rows)} 条（{mode_counts}）。"
            f" 黄色阈值 >= {self.fees.yellow_threshold:.2f} 元，"
            f" 红色/声音阈值 >= {self.fees.red_threshold:.2f} 元，"
            f" 当前声音报警：{sound_text}。"
            " 红黄高亮：保底收益始终参与；条件结构在符合行权方向时按若被行权收益参与高亮。"
        )

    def _update_recommendations(self, rows: list[dict[str, Any]]) -> None:
        self.recommendation_label.setText(
            self._build_recommendation_text(
                build_recommendations(rows, limit=3),
                empty_text="推荐1-3：当前没有可直接下手的正收益候选，建议继续等待盘口变化。",
            )
        )
        self.recommendation_guidance_label.setText(recommendation_guidance_html(rows))

        selected_pools = sorted(self._selected_pool_names())
        pool_hint = "、".join(selected_pools) if selected_pools else "未勾选品种"
        filtered_rows = self._display_filtered_rows(rows)
        self.filtered_recommendation_label.setText(
            self._build_recommendation_text(
                build_recommendations(filtered_rows, limit=3),
                empty_text=f"当前筛选推荐：{pool_hint} 下暂无正收益候选。",
                title_prefix=f"当前筛选推荐（{pool_hint}）",
            )
        )

    def _build_recommendation_text(
        self,
        picks: list[dict[str, Any]],
        *,
        empty_text: str,
        title_prefix: str = "",
    ) -> str:
        if not picks:
            return empty_text

        lines = []
        if title_prefix:
            lines.append(f"{title_prefix}：")
        for index, row in enumerate(picks, start=1):
            upper_profit = row.get("exercise_upper_profit")
            upper_text = (
                f"，若被行权收益 {float(upper_profit):.2f} 元"
                if upper_profit is not None
                else ""
            )
            effective_label = recommendation_profit_label(row)
            effective_profit = recommendation_effective_profit(row)
            lines.append(
                f"推荐{index}：{row['mode_key']} {row['pool']} "
                f"K={format_strike_display(float(row['strike']), str(row.get('spot_code', '')))}，"
                f"{effective_label} {effective_profit:.2f} 元，"
                f"{row.get('moneyness_text', '')}{upper_text}；"
                f"公式：{self._recommendation_formula_text(row)}"
            )
        if any(not bool(row.get("alert_eligible")) for row in picks):
            lines.append("说明：条件结构仅在符合行权方向时，按若被行权收益参与推荐排序。")
        return "\n".join(lines)

    def _recommendation_formula_text(self, row: dict[str, Any]) -> str:
        multiplier = float(self.fees.multiplier)
        stock_commission = float(self.fees.stock_commission_rate)
        option_open_fee = float(self.fees.option_open_fee)
        option_exercise_fee = float(self.fees.option_exercise_fee)
        stock_borrow_cost = float(self.fees.stock_borrow_cost)
        strike = float(row.get("strike", 0.0))
        spot_bid = float(row.get("spot_bid", 0.0))
        spot_ask = float(row.get("spot_ask", 0.0))
        option_bid = float(row.get("option_bid", 0.0))
        option_ask = float(row.get("option_ask", 0.0))
        effective_profit = recommendation_effective_profit(row)
        effective_label = recommendation_profit_label(row)
        mode_key = str(row.get("mode_key", ""))

        if mode_key == "模式1":
            return (
                f"{effective_label} = {strike:.4f}×{multiplier:.0f}"
                f" - [{spot_ask:.4f}×{multiplier:.0f}×(1+{stock_commission:.6f})"
                f" + {option_ask:.4f}×{multiplier:.0f} + {option_open_fee:.2f} + {option_exercise_fee:.2f}]"
                f" = {effective_profit:.2f} 元"
            )
        if mode_key == "模式2":
            return (
                f"{effective_label} = {spot_bid:.4f}×{multiplier:.0f}×(1-{stock_commission:.6f})"
                f" + {option_bid:.4f}×{multiplier:.0f} - {strike:.4f}×{multiplier:.0f}"
                f" = {effective_profit:.2f} 元"
            )
        if mode_key == "模式3":
            if effective_label == "若被行权收益":
                return (
                    f"{effective_label} = {strike:.4f}×{multiplier:.0f}"
                    f" + {option_bid:.4f}×{multiplier:.0f}"
                    f" - {spot_ask:.4f}×{multiplier:.0f}×(1+{stock_commission:.6f})"
                    f" = {effective_profit:.2f} 元"
                )
            return (
                f"{effective_label} = {spot_bid:.4f}×{multiplier:.0f}×(1-{stock_commission:.6f})"
                f" + {option_bid:.4f}×{multiplier:.0f}"
                f" - {spot_ask:.4f}×{multiplier:.0f}×(1+{stock_commission:.6f})"
                f" = {effective_profit:.2f} 元"
            )
        if mode_key == "模式4":
            return (
                f"{effective_label} = {spot_bid:.4f}×{multiplier:.0f}×(1-{stock_commission:.6f})"
                f" - [{strike:.4f}×{multiplier:.0f} + {option_ask:.4f}×{multiplier:.0f}"
                f" + {option_open_fee:.2f} + {option_exercise_fee:.2f} + {stock_borrow_cost:.2f}]"
                f" = {effective_profit:.2f} 元"
            )
        return f"{effective_label} = {effective_profit:.2f} 元"

    def _selected_atm_tiers(self) -> set[int]:
        return {tier for tier, checkbox in self.tier_checkboxes.items() if checkbox.isChecked()}

    def on_tier_filter_changed(self, _checked: bool) -> None:
        self.on_display_filter_changed(_checked)

    def on_display_filter_changed(self, _checked: bool) -> None:
        if self.is_frozen:
            return
        if self.latest_rows:
            self.render_rows(self.latest_rows)
            self._update_recommendations(self.latest_rows)

    def _display_filtered_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        selected_tiers = self._selected_atm_tiers()
        selected_pools = self._selected_pool_names()
        hide_adjusted = self.hide_adjusted_checkbox.isChecked()
        filtered = [
            row
            for row in rows
            if int(row.get("atm_tier", 0)) in selected_tiers
            and str(row.get("pool", "")) in selected_pools
            and not (hide_adjusted and bool(row.get("is_adjusted")))
        ]
        filtered.sort(key=recommendation_rank_key)
        return filtered

    def _rows_for_mode(self, rows: list[dict[str, Any]], mode_key: str) -> list[dict[str, Any]]:
        filtered = [
            row
            for row in self._display_filtered_rows(rows)
            if row.get("mode_key") == mode_key
        ]
        return sort_mode_rows_by_strike(filtered)

    def render_rows(self, rows: list[dict[str, Any]]) -> None:
        for mode_key, _, _ in ARBITRAGE_MODE_DEFS:
            mode_rows = self._rows_for_mode(rows, mode_key)
            self.rendered_rows_by_mode[mode_key] = mode_rows
            self._set_mode_box_count(mode_key, len(mode_rows))
            self._render_mode_table(self.mode_tables[mode_key], mode_rows)

    def _render_mode_table(self, table: QTableWidget, rows: list[dict[str, Any]]) -> None:
        table.setSortingEnabled(False)
        table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = [
                row["pool"],
                row["option_code"],
                format_strike_display(float(row["strike"]), str(row.get("spot_code", ""))),
                str(row.get("tier_label") or format_atm_tier_label(int(row.get("atm_tier", 0)))),
                f"{row['profit']:.2f}",
                (
                    f"{float(row['exercise_upper_profit']):.2f}"
                    if row.get("exercise_upper_profit") is not None
                    else "-"
                ),
                row.get("profit_type", ""),
                row.get("moneyness_text", ""),
                row.get("exercise_status", ""),
                f"{row['spot_bid']:.4f}",
                f"{row['spot_ask']:.4f}",
                f"{row['option_bid']:.4f}",
                f"{row['option_ask']:.4f}",
                f"{float(row['intrinsic_value']):.4f}",
                f"{float(row['time_value']):.4f}",
                row["expiry"],
                row["updated_at"],
                row.get("exercise_condition", ""),
                row["action"],
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column in self._NUMERIC_TABLE_COLUMNS:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self._apply_quote_column_group_style(item, column)
                if column == self._PROFIT_COLUMN:
                    self._apply_profit_color(item, float(row["profit"]), bool(row.get("alert_eligible")))
                if column == self._UPPER_PROFIT_COLUMN:
                    self._apply_upper_profit_color(
                        item,
                        row.get("exercise_upper_profit"),
                        highlight_eligible=(
                            not bool(row.get("alert_eligible"))
                            and bool(row.get("is_in_the_money"))
                        ),
                    )
                if column == self._TIME_VALUE_COLUMN and float(row["time_value"]) < 0:
                    item.setForeground(QColor("#d90429"))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                if column == 6:
                    self._apply_profit_type_style(item, bool(row.get("alert_eligible")))
                if column == 7:
                    self._apply_moneyness_style(item, str(row.get("moneyness_text", "")))
                if column == self._EXERCISE_STATUS_COLUMN:
                    self._apply_exercise_status_alert(item, str(row.get("exercise_status", "")))
                table.setItem(row_index, column, item)
        table.resizeColumnsToContents()
        table.setSortingEnabled(True)

    @classmethod
    def _apply_quote_column_group_style(
        cls,
        item: QTableWidgetItem,
        column: int,
        *,
        is_header: bool = False,
    ) -> None:
        style = cls._QUOTE_COLUMN_GROUP_STYLES.get(column)
        if style is None:
            return
        header_color, cell_color, text_color = style
        item.setBackground(QColor(header_color if is_header else cell_color))
        item.setForeground(QColor(text_color))

    @staticmethod
    def _exercise_status_alert_style(text: str) -> tuple[str, str] | None:
        if "需主动行权" in text:
            return "#d90429", "#ffffff"
        if "可能被行权" in text:
            return "#ffe66d", "#7a4300"
        return None

    def _apply_exercise_status_alert(self, item: QTableWidgetItem, text: str) -> None:
        style = self._exercise_status_alert_style(text)
        if style is None:
            return
        background, foreground = style
        item.setBackground(QColor(background))
        item.setForeground(QColor(foreground))
        font = item.font()
        font.setBold(True)
        item.setFont(font)

    def _apply_profit_color(self, item: QTableWidgetItem, profit: float, alert_eligible: bool) -> None:
        if not alert_eligible:
            if profit > 0:
                item.setBackground(QColor("#e3f2fd"))
                item.setForeground(QColor("#0d47a1"))
            elif profit < 0:
                item.setForeground(QColor("#666666"))
            return
        if profit >= self.fees.red_threshold:
            item.setBackground(QColor("#d90429"))
            item.setForeground(QColor("#ffffff"))
        elif profit >= self.fees.yellow_threshold:
            item.setBackground(QColor("#ffe66d"))
            item.setForeground(QColor("#111111"))
        elif profit < 0:
            item.setForeground(QColor("#666666"))

    @staticmethod
    def _apply_profit_type_style(item: QTableWidgetItem, alert_eligible: bool) -> None:
        if alert_eligible:
            item.setForeground(QColor("#0b7a3b"))
        else:
            item.setForeground(QColor("#0d47a1"))

    def _apply_upper_profit_color(
        self,
        item: QTableWidgetItem,
        profit: Any,
        *,
        highlight_eligible: bool,
    ) -> None:
        if profit is None:
            item.setForeground(QColor("#777777"))
            return
        try:
            value = float(profit)
        except (TypeError, ValueError):
            item.setForeground(QColor("#777777"))
            return
        if highlight_eligible:
            if value >= self.fees.red_threshold:
                item.setBackground(QColor("#d90429"))
                item.setForeground(QColor("#ffffff"))
                return
            if value >= self.fees.yellow_threshold:
                item.setBackground(QColor("#ffe66d"))
                item.setForeground(QColor("#111111"))
                return
        if value > 0:
            item.setBackground(QColor("#eef6ff"))
            item.setForeground(QColor("#0d47a1"))
        elif value < 0:
            item.setForeground(QColor("#666666"))

    @staticmethod
    def _apply_moneyness_style(item: QTableWidgetItem, text: str) -> None:
        if text == "行权价低于现价":
            item.setForeground(QColor("#b54708"))
        elif text == "行权价高于现价":
            item.setForeground(QColor("#555555"))

    def toggle_freeze(self) -> None:
        self.is_frozen = not self.is_frozen
        if self.is_frozen:
            self.freeze_button.setText("解锁")
            self.summary_label.setText("画面已锁定：后台仍在接收行情与计算套利，声音开关仍可正常使用。")
        else:
            self.freeze_button.setText("锁定")
            self.render_rows(self.latest_rows)
            self.on_rows_ready(self.latest_rows)

    def on_sound_toggled(self, checked: bool) -> None:
        if hasattr(self, "worker"):
            self.worker.set_sound_enabled(checked)
        self.config.setdefault("fees", {})
        self.config["fees"]["sound_enabled"] = checked
        save_app_config(self.config_path, self.config)
        self.fees = FeeConfig.from_dict(self.config["fees"])
        if self.latest_rows:
            self.on_rows_ready(self.latest_rows)

    def show_formula_explanation(self) -> None:
        QMessageBox.information(self, "四模式公式说明", FORMULA_EXPLANATION_TEXT)

    def _selected_ledger_prefill(self) -> dict[str, Any] | None:
        for mode_key, table in self.mode_tables.items():
            selected_rows = table.selectionModel().selectedRows()
            if not selected_rows:
                continue
            row_index = selected_rows[0].row()
            rendered_rows = self.rendered_rows_by_mode.get(mode_key, [])
            if row_index < 0 or row_index >= len(rendered_rows):
                continue
            mapping = LEDGER_PREFILL_QUOTE_FIELDS.get(mode_key)
            if mapping is None:
                continue
            row = rendered_rows[row_index]
            ledger_mode, spot_field, option_field = mapping
            spot_code = str(row.get("spot_code") or row.get("pool", "")).split(".")[0]
            return {
                "mode": ledger_mode,
                "etf_code": spot_code,
                "option_code": str(row.get("option_code", "")),
                "strike": float(row.get("strike", 0.0)),
                "stock_price": float(row.get(spot_field, 0.0)),
                "option_premium": round(float(row.get(option_field, 0.0)) * 10000, 2),
                "stock_shares": 10000,
                "option_contracts": 1,
            }
        return None

    def open_post_market_ledger(self) -> None:
        dialog = StrategyLedgerDialog(self.config_path.parent, self)
        prefill = self._selected_ledger_prefill()
        if prefill is not None:
            dialog.apply_prefill(prefill)
        dialog.exec()

    def open_config_dialog(self) -> None:
        dialog = ConfigDialog(
            load_app_config(self.config_path),
            self,
            diagnostic_text=self._format_diagnostic_text(self.latest_diagnostic_info)
            if self.latest_diagnostic_info
            else "",
        )
        self.config_dialog = dialog
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self.config_dialog = None
            return
        try:
            config = dialog.to_config()
            save_app_config(self.config_path, config)
        except ValueError as exc:
            self.config_dialog = None
            QMessageBox.warning(self, "配置保存失败", str(exc))
            return

        self.config = config
        self.fees = FeeConfig.from_dict(self.config["fees"])
        self._rebuild_pool_filter_widgets()
        self.sound_checkbox.blockSignals(True)
        self.sound_checkbox.setChecked(self.fees.sound_enabled)
        self.sound_checkbox.blockSignals(False)
        self.config_dialog = None
        QMessageBox.information(self, "配置已保存", "配置已写入文件，后台线程将自动重启并加载新配置。")
        self._restart_worker()

    def reload_config(self) -> None:
        answer = QMessageBox.question(
            self,
            "重新读取配置",
            "重新读取配置会重启后台行情线程，确认继续吗？",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self.config = load_app_config(self.config_path)
        self.fees = FeeConfig.from_dict(self.config["fees"])
        self._rebuild_pool_filter_widgets()
        self.sound_checkbox.blockSignals(True)
        self.sound_checkbox.setChecked(self.fees.sound_enabled)
        self.sound_checkbox.blockSignals(False)
        self._restart_worker()

    def closeEvent(self, event: Any) -> None:
        if hasattr(self, "worker"):
            self.worker.stop()
            self.worker.wait(2000)
        event.accept()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="A股ETF期权交割套利机会扫描器")
    parser.add_argument("--config", default=CONFIG_FILE, help="配置文件路径，默认 contracts_config.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path = resolve_config_path(args.config)
    config = load_app_config(config_path)
    if "sound_enabled" not in config.get("fees", {}):
        config.setdefault("fees", {})
        config["fees"]["sound_enabled"] = False
        save_app_config(config_path, config)

    app = QApplication(sys.argv)
    window = MainWindow(config_path)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
