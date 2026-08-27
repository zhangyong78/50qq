from __future__ import annotations

import json
import math
import uuid
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QDialog,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

OPTION_MULTIPLIER = 10000
VALID_MODES = frozenset({"mode1", "mode2", "mode3", "mode4"})
MODE_LABELS = {
    "mode1": "模式1：买入认沽 + 买入现货",
    "mode2": "模式2：卖出认沽 + 卖出现货",
    "mode3": "模式3：卖出认购 + 买入/持有现货",
    "mode4": "模式4：买入认购 + 卖出现货",
}
PASSIVE_SETTLEMENT_MODES = frozenset({"mode2", "mode3"})


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
    commission = _number(record, "stock_commission_rate", 0.0001)
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
    commission = _number(record, "stock_commission_rate", 0.0001)
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
    def __init__(self, config_dir: Path) -> None:
        self.config_dir = Path(config_dir)
        self.data_path = self.config_dir / "strategy_ledger.json"
        self.legacy_data_dir = self.config_dir / "strategy_ledger_data"

    @staticmethod
    def _read_records(path: Path) -> list[dict[str, Any]]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Unable to read ledger: {exc}") from exc
        if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
            raise ValueError("Ledger must contain a record list")
        return [dict(item) for item in payload]

    def load_all(self) -> list[dict[str, Any]]:
        if self.data_path.exists():
            return self._read_records(self.data_path)
        if not self.legacy_data_dir.exists():
            return []

        # Preserve earlier monthly files until the user saves into the new single file.
        records: list[dict[str, Any]] = []
        for path in sorted(self.legacy_data_dir.glob("*.json")):
            records.extend(self._read_records(path))
        return records

    def save_all(self, records: list[dict[str, Any]]) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        temporary_path = self.data_path.with_suffix(".json.tmp")
        temporary_path.write_text(
            json.dumps(records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary_path.replace(self.data_path)


class StrategyLedgerDialog(QDialog):
    TABLE_HEADERS = [
        "结算日",
        "模式",
        "ETF",
        "期权代码",
        "行权价",
        "现货股数",
        "期权张数",
        "现货成交价",
        "期权权利金(元/张)",
        "已结算利润(元)",
        "结算公式",
        "备注",
    ]

    def __init__(self, config_dir: Path, parent=None) -> None:
        super().__init__(parent)
        self.store = StrategyLedgerStore(Path(config_dir))
        self.all_records: list[dict[str, Any]] = []
        self.records: list[dict[str, Any]] = []
        self.editing_record_id: str | None = None
        self.setWindowTitle("盘后策略账本")
        self.resize(1480, 760)
        self._build_ui()
        self.load_selected_month()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        summary_layout = QHBoxLayout()
        summary_layout.addWidget(QLabel("账本月份："))
        self.month_edit = QDateEdit(QDate.currentDate(), self)
        self.month_edit.setDisplayFormat("yyyy-MM")
        self.month_edit.setCalendarPopup(True)
        self.month_edit.dateChanged.connect(self.load_selected_month)
        summary_layout.addWidget(self.month_edit)
        self.month_total_label = QLabel("本月已结算利润：¥0.00")
        self.month_total_label.setStyleSheet(
            "font-size:18px; font-weight:600; color:#006b5b; padding:4px 12px;"
            "background:#eefaf7; border:1px solid #b9e3d9; border-radius:4px;"
        )
        self.record_count_label = QLabel("0 条记录")
        self.record_count_label.setStyleSheet("color:#555555;")
        summary_layout.addWidget(self.month_total_label)
        summary_layout.addWidget(self.record_count_label)
        summary_layout.addStretch(1)
        layout.addLayout(summary_layout)

        form_box = QGroupBox("录入已行权/被指派单子", self)
        form = QGridLayout(form_box)
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(6)

        self.mode_combo = QComboBox(self)
        for mode, label in MODE_LABELS.items():
            self.mode_combo.addItem(label, mode)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self.settlement_date_edit = QDateEdit(QDate.currentDate(), self)
        self.settlement_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.settlement_date_edit.setCalendarPopup(True)
        self.etf_code_edit = QLineEdit("510050", self)
        self.option_code_edit = QLineEdit(self)
        self.option_code_edit.setPlaceholderText("如 100xxxx.SH")
        self.strike_spin = self._money_spin(4, 100.0)
        self.stock_shares_spin = QSpinBox(self)
        self.stock_shares_spin.setRange(1, 100000000)
        self.stock_shares_spin.setSingleStep(10000)
        self.stock_shares_spin.setValue(10000)
        self.stock_price_label = QLabel("现货买入价")
        self.stock_price_spin = self._money_spin(6, 10000.0)
        self.option_contracts_spin = QSpinBox(self)
        self.option_contracts_spin.setRange(1, 10000)
        self.option_contracts_spin.setValue(1)
        self.option_premium_label = QLabel("认沽买入权利金(元/张)")
        self.option_premium_spin = self._money_spin(2, 1000000.0)
        self.commission_spin = self._money_spin(6, 1.0)
        self.commission_spin.setValue(0.0001)
        self.option_buy_open_fee_spin = self._money_spin(2, 10000.0)
        self.option_buy_open_fee_spin.setValue(2.0)
        self.active_exercise_fee_spin = self._money_spin(2, 10000.0)
        self.active_exercise_fee_spin.setValue(4.0)
        self.borrow_cost_spin = self._money_spin(2, 10000000.0)
        self.note_edit = QLineEdit(self)
        self.note_edit.setPlaceholderText("可选备注")

        fields = [
            ("策略模式", self.mode_combo),
            ("结算日期", self.settlement_date_edit),
            ("ETF代码", self.etf_code_edit),
            ("期权代码", self.option_code_edit),
            ("行权价", self.strike_spin),
            ("现货股数", self.stock_shares_spin),
            (self.stock_price_label, self.stock_price_spin),
            ("期权张数", self.option_contracts_spin),
            (self.option_premium_label, self.option_premium_spin),
            ("现货佣金率", self.commission_spin),
            ("买入开仓费(元/张)", self.option_buy_open_fee_spin),
            ("主动行权费(元/张)", self.active_exercise_fee_spin),
            ("融券/资金成本(元)", self.borrow_cost_spin),
            ("备注", self.note_edit),
        ]
        for index, (label, widget) in enumerate(fields):
            row = index // 4
            column = (index % 4) * 2
            form.addWidget(label if isinstance(label, QLabel) else QLabel(label), row, column)
            form.addWidget(widget, row, column + 1)

        self.save_button = QPushButton("新增记录", self)
        self.save_button.clicked.connect(self.save_form_record)
        self.clear_button = QPushButton("清空输入", self)
        self.clear_button.clicked.connect(self.clear_form)
        self.delete_button = QPushButton("删除选中记录", self)
        self.delete_button.clicked.connect(self.delete_selected_record)
        self.save_button.setStyleSheet("background:#007f72; color:white; font-weight:600; padding:5px 12px;")
        self.delete_button.setStyleSheet("background:#b42318; color:white; padding:5px 12px;")
        form.addWidget(self.save_button, 4, 5)
        form.addWidget(self.clear_button, 4, 6)
        form.addWidget(self.delete_button, 4, 7)
        layout.addWidget(form_box)

        self.status_label = QLabel("所有记录按已行权或被指派的实际结果结算。")
        self.status_label.setStyleSheet("color:#555555;")
        layout.addWidget(self.status_label)

        self.table = QTableWidget(0, len(self.TABLE_HEADERS), self)
        self.table.setHorizontalHeaderLabels(self.TABLE_HEADERS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setColumnWidth(10, 520)
        self.table.setColumnWidth(11, 200)
        self.table.itemSelectionChanged.connect(self.load_selected_record_into_form)
        layout.addWidget(self.table, stretch=1)
        self._on_mode_changed()

    @staticmethod
    def _money_spin(decimals: int, maximum: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setDecimals(decimals)
        spin.setRange(0.0, maximum)
        spin.setSingleStep(0.01 if decimals <= 2 else 0.0001)
        return spin

    def selected_month_text(self) -> str:
        return self.month_edit.date().toString("yyyy-MM")

    def _mode(self) -> str:
        return str(self.mode_combo.currentData())

    def _on_mode_changed(self) -> None:
        mode = self._mode()
        labels = {
            "mode1": ("现货买入价", "认沽买入权利金(元/张)"),
            "mode2": ("现货卖出价", "认沽卖出权利金(元/张)"),
            "mode3": ("现货买入价", "认购买出权利金(元/张)"),
            "mode4": ("现货卖出价", "认购买入权利金(元/张)"),
        }
        stock_label, premium_label = labels[mode]
        self.stock_price_label.setText(stock_label)
        self.option_premium_label.setText(premium_label)
        passive = mode in PASSIVE_SETTLEMENT_MODES
        self.option_buy_open_fee_spin.setEnabled(not passive)
        self.active_exercise_fee_spin.setEnabled(not passive)
        if passive:
            self.option_buy_open_fee_spin.setValue(0.0)
            self.active_exercise_fee_spin.setValue(0.0)
        else:
            if self.option_buy_open_fee_spin.value() == 0.0:
                self.option_buy_open_fee_spin.setValue(2.0)
            if self.active_exercise_fee_spin.value() == 0.0:
                self.active_exercise_fee_spin.setValue(4.0)

    def load_selected_month(self) -> None:
        self.editing_record_id = None
        try:
            self.all_records = self.store.load_all()
            month_text = self.selected_month_text()
            self.records = [
                record
                for record in self.all_records
                if str(record.get("settlement_date", ""))[:7] == month_text
            ]
        except ValueError as exc:
            self.all_records = []
            self.records = []
            self.status_label.setText(str(exc))
        self.refresh_view()

    def refresh_view(self) -> None:
        total = sum(float(record.get("result", 0.0)) for record in self.records)
        self.month_total_label.setText(f"本月已结算利润：¥{total:,.2f}")
        self.record_count_label.setText(f"{len(self.records)} 条记录")
        self.table.setRowCount(len(self.records))
        for row_index, record in enumerate(self.records):
            values = [
                record.get("settlement_date", ""),
                MODE_LABELS.get(str(record.get("mode", "")), ""),
                record.get("etf_code", ""),
                record.get("option_code", ""),
                f"{float(record.get('strike', 0.0)):.4f}",
                str(record.get("stock_shares", "")),
                str(record.get("option_contracts", "")),
                f"{float(record.get('stock_price', 0.0)):.4f}",
                f"{float(record.get('option_premium', 0.0)):.2f}",
                f"{float(record.get('result', 0.0)):.2f}",
                record.get("formula", ""),
                record.get("note", ""),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column in {4, 5, 6, 7, 8, 9}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row_index, column, item)
        self.status_label.setText("所有记录按已行权或被指派的实际结果结算。")

    def _record_from_form(self) -> dict[str, Any] | None:
        etf_code = self.etf_code_edit.text().strip().upper()
        if not etf_code:
            QMessageBox.warning(self, "盘后策略账本", "请填写 ETF 代码。")
            return None
        record = {
            "id": self.editing_record_id or uuid.uuid4().hex,
            "settlement_date": self.settlement_date_edit.date().toString("yyyy-MM-dd"),
            "mode": self._mode(),
            "etf_code": etf_code,
            "option_code": self.option_code_edit.text().strip().upper(),
            "strike": self.strike_spin.value(),
            "stock_shares": self.stock_shares_spin.value(),
            "stock_price": self.stock_price_spin.value(),
            "option_contracts": self.option_contracts_spin.value(),
            "option_premium": self.option_premium_spin.value(),
            "stock_commission_rate": self.commission_spin.value(),
            "option_buy_open_fee": self.option_buy_open_fee_spin.value(),
            "active_exercise_fee": self.active_exercise_fee_spin.value(),
            "borrow_cost": self.borrow_cost_spin.value(),
            "note": self.note_edit.text().strip(),
        }
        if record["settlement_date"][:7] != self.selected_month_text():
            QMessageBox.warning(self, "盘后策略账本", "结算日期必须属于当前账本月份。")
            return None
        try:
            validate_settlement_record(record)
        except ValueError as exc:
            QMessageBox.warning(self, "盘后策略账本", str(exc))
            return None
        record["result"] = calculate_settled_profit(record)
        record["formula"] = format_settlement_formula(record)
        return record

    def save_form_record(self) -> None:
        record = self._record_from_form()
        if record is None:
            return
        if self.editing_record_id is None:
            self.all_records.append(record)
        else:
            for index, existing in enumerate(self.all_records):
                if str(existing.get("id", "")) == self.editing_record_id:
                    self.all_records[index] = record
                    break
        self._persist_and_refresh()
        self.clear_form()

    def delete_selected_record(self) -> None:
        if self.editing_record_id is None:
            QMessageBox.information(self, "盘后策略账本", "请先选中一条记录。")
            return
        self.all_records = [
            record
            for record in self.all_records
            if str(record.get("id", "")) != self.editing_record_id
        ]
        self._persist_and_refresh()
        self.clear_form()

    def load_selected_record_into_form(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        record = self.records[rows[0].row()]
        self.editing_record_id = str(record.get("id", "")) or None
        mode_index = self.mode_combo.findData(record.get("mode", "mode1"))
        self.mode_combo.setCurrentIndex(max(mode_index, 0))
        self.settlement_date_edit.setDate(QDate.fromString(str(record.get("settlement_date", "")), "yyyy-MM-dd"))
        self.etf_code_edit.setText(str(record.get("etf_code", "")))
        self.option_code_edit.setText(str(record.get("option_code", "")))
        self.strike_spin.setValue(float(record.get("strike", 0.0)))
        self.stock_shares_spin.setValue(int(record.get("stock_shares", 10000)))
        self.stock_price_spin.setValue(float(record.get("stock_price", 0.0)))
        self.option_contracts_spin.setValue(int(record.get("option_contracts", 1)))
        self.option_premium_spin.setValue(float(record.get("option_premium", 0.0)))
        self.commission_spin.setValue(float(record.get("stock_commission_rate", 0.0001)))
        self.option_buy_open_fee_spin.setValue(float(record.get("option_buy_open_fee", 0.0)))
        self.active_exercise_fee_spin.setValue(float(record.get("active_exercise_fee", 0.0)))
        self.borrow_cost_spin.setValue(float(record.get("borrow_cost", 0.0)))
        self.note_edit.setText(str(record.get("note", "")))
        self.save_button.setText("保存修改")

    def clear_form(self) -> None:
        self.editing_record_id = None
        self.table.clearSelection()
        self.settlement_date_edit.setDate(self.month_edit.date())
        self.option_code_edit.clear()
        self.strike_spin.setValue(0.0)
        self.stock_shares_spin.setValue(10000)
        self.stock_price_spin.setValue(0.0)
        self.option_contracts_spin.setValue(1)
        self.option_premium_spin.setValue(0.0)
        self.commission_spin.setValue(0.0001)
        self.borrow_cost_spin.setValue(0.0)
        self.note_edit.clear()
        self.save_button.setText("新增记录")
        self._on_mode_changed()

    def apply_prefill(self, prefill: dict[str, Any]) -> None:
        self.clear_form()
        mode_index = self.mode_combo.findData(str(prefill.get("mode", "mode1")))
        self.mode_combo.setCurrentIndex(max(mode_index, 0))
        self.etf_code_edit.setText(str(prefill.get("etf_code", "")))
        self.option_code_edit.setText(str(prefill.get("option_code", "")))
        self.strike_spin.setValue(float(prefill.get("strike", 0.0)))
        self.stock_price_spin.setValue(float(prefill.get("stock_price", 0.0)))
        self.option_premium_spin.setValue(float(prefill.get("option_premium", 0.0)))
        self.stock_shares_spin.setValue(int(prefill.get("stock_shares", 10000)))
        self.option_contracts_spin.setValue(int(prefill.get("option_contracts", 1)))
        self.save_button.setText("新增记录")

    def _persist_and_refresh(self) -> None:
        try:
            self.store.save_all(self.all_records)
        except OSError as exc:
            QMessageBox.critical(self, "盘后策略账本", f"保存账本失败：{exc}")
            return
        month_text = self.selected_month_text()
        self.records = [
            record
            for record in self.all_records
            if str(record.get("settlement_date", ""))[:7] == month_text
        ]
        self.refresh_view()
