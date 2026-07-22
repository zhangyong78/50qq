from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
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
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


APP_NAME = "ETF期权交易小账本"
OPTION_MULTIPLIER = 10_000


def application_data_dir() -> Path:
    """Use a writable folder beside the script or packaged executable."""
    base_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    return base_dir / "ledger_data"


def trade_multiplier(instrument_type: str) -> int:
    return OPTION_MULTIPLIER if instrument_type == "期权" else 1


def trade_gross_amount(record: dict[str, Any]) -> float:
    price = float(record.get("price", 0.0))
    quantity = float(record.get("quantity", 0.0))
    return round(price * quantity * trade_multiplier(str(record.get("instrument_type", "现货"))), 2)


def calculate_day_summary(records: list[dict[str, Any]]) -> dict[str, float]:
    buy_amount = sum(trade_gross_amount(record) for record in records if record.get("direction") == "买入")
    sell_amount = sum(trade_gross_amount(record) for record in records if record.get("direction") == "卖出")
    fee_amount = sum(float(record.get("fee", 0.0)) for record in records)
    return {
        "buy_amount": round(buy_amount, 2),
        "sell_amount": round(sell_amount, 2),
        "fee_amount": round(fee_amount, 2),
        "net_profit": round(sell_amount - buy_amount - fee_amount, 2),
    }


def normalize_record(record: dict[str, Any], date_text: str) -> dict[str, Any]:
    instrument_type = str(record.get("instrument_type", "现货"))
    direction = str(record.get("direction", "买入"))
    return {
        "date": date_text,
        "instrument_type": instrument_type if instrument_type in {"现货", "期权"} else "现货",
        "direction": direction if direction in {"买入", "卖出"} else "买入",
        "code": str(record.get("code", "")).strip().upper(),
        "price": round(float(record.get("price", 0.0)), 6),
        "quantity": int(record.get("quantity", 0)),
        "fee": round(float(record.get("fee", 0.0)), 2),
        "note": str(record.get("note", "")).strip(),
    }


class LedgerStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.last_error = ""

    def _path_for_date(self, date_text: str) -> Path:
        try:
            datetime.strptime(date_text, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("日期格式必须为 YYYY-MM-DD") from exc
        return self.data_dir / f"{date_text}.json"

    def load(self, date_text: str) -> list[dict[str, Any]]:
        self.last_error = ""
        path = self._path_for_date(date_text)
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, list):
                raise ValueError("账本文件格式不是记录列表")
            return [dict(item) for item in payload if isinstance(item, dict)]
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self.last_error = f"无法读取 {path.name}：{exc}"
            return []

    def save(self, date_text: str, records: list[dict[str, Any]]) -> None:
        self.last_error = ""
        path = self._path_for_date(date_text)
        normalized = [dict(record) for record in records]
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            temporary_path = path.with_suffix(".json.tmp")
            temporary_path.write_text(
                json.dumps(normalized, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temporary_path.replace(path)
        except OSError as exc:
            self.last_error = f"无法保存 {path.name}：{exc}"
            raise


class LedgerWindow(QMainWindow):
    HEADERS = ["日期", "品种", "方向", "代码", "价格", "数量", "成交金额", "手续费", "备注"]

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(1120, 680)
        self.store = LedgerStore(application_data_dir())
        self.records: list[dict[str, Any]] = []
        self.editing_index: int | None = None
        self._build_ui()
        self.load_selected_date()

    def _build_ui(self) -> None:
        root = QWidget(self)
        root.setStyleSheet(
            "QWidget { font-family: 'Microsoft YaHei'; font-size: 13px; }"
            "QGroupBox { font-weight: 600; border: 1px solid #cbd5d8; border-radius: 6px; margin-top: 10px; padding: 10px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }"
            "QPushButton { background: #0f766e; color: white; border: 0; border-radius: 4px; padding: 7px 15px; font-weight: 600; }"
            "QPushButton:hover { background: #115e59; }"
            "QPushButton#secondary { background: #e7eceb; color: #1f2937; }"
            "QPushButton#danger { background: #b91c1c; }"
            "QTableWidget { gridline-color: #d6dddc; alternate-background-color: #f4f8f7; }"
        )
        layout = QVBoxLayout(root)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel(APP_NAME)
        title.setStyleSheet("font-size: 21px; font-weight: 700; color: #134e4a;")
        subtitle = QLabel("当天现金流：卖出金额 - 买入金额 - 手续费")
        subtitle.setStyleSheet("color: #64748b; padding-left: 12px;")
        header.addWidget(title)
        header.addWidget(subtitle)
        header.addStretch(1)
        header.addWidget(QLabel("账本日期："))
        self.date_edit = QDateEdit(QDate.currentDate(), self)
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.dateChanged.connect(self.load_selected_date)
        header.addWidget(self.date_edit)
        layout.addLayout(header)

        summary_frame = QFrame(self)
        summary_frame.setStyleSheet("QFrame { background: #edf7f4; border: 1px solid #b7ddd2; border-radius: 7px; }")
        summary_layout = QHBoxLayout(summary_frame)
        summary_layout.setContentsMargins(14, 10, 14, 10)
        self.summary_labels: dict[str, QLabel] = {}
        for key, caption in (
            ("buy_amount", "买入金额"),
            ("sell_amount", "卖出金额"),
            ("fee_amount", "手续费"),
            ("net_profit", "当天净利润"),
        ):
            box = QVBoxLayout()
            caption_label = QLabel(caption)
            caption_label.setStyleSheet("color: #475569;")
            value_label = QLabel("¥0.00")
            value_label.setStyleSheet("font-size: 19px; font-weight: 700; color: #0f766e;")
            box.addWidget(caption_label)
            box.addWidget(value_label)
            summary_layout.addLayout(box)
            summary_layout.addStretch(1)
            self.summary_labels[key] = value_label
        layout.addWidget(summary_frame)

        form_box = QGroupBox("录入单子", self)
        form_layout = QGridLayout(form_box)
        form_layout.setHorizontalSpacing(10)
        form_layout.setVerticalSpacing(8)
        self.instrument_combo = QComboBox(self)
        self.instrument_combo.addItems(["现货", "期权"])
        self.direction_combo = QComboBox(self)
        self.direction_combo.addItems(["买入", "卖出"])
        self.code_edit = QLineEdit(self)
        self.code_edit.setPlaceholderText("如 510050.SH 或 100xxxxx.SH")
        self.price_spin = self._amount_spin(6, 1_000_000.0)
        self.quantity_spin = QSpinBox(self)
        self.quantity_spin.setRange(1, 1_000_000_000)
        self.quantity_spin.setValue(1)
        self.fee_spin = self._amount_spin(2, 1_000_000.0)
        self.note_edit = QLineEdit(self)
        self.note_edit.setPlaceholderText("可选备注")

        fields = [
            ("品种", self.instrument_combo),
            ("方向", self.direction_combo),
            ("代码", self.code_edit),
            ("价格", self.price_spin),
            ("数量", self.quantity_spin),
            ("手续费", self.fee_spin),
            ("备注", self.note_edit),
        ]
        for index, (caption, widget) in enumerate(fields):
            row = index // 4
            column = (index % 4) * 2
            form_layout.addWidget(QLabel(caption), row, column)
            form_layout.addWidget(widget, row, column + 1)

        self.save_button = QPushButton("新增记录", self)
        self.save_button.clicked.connect(self.save_form_record)
        self.clear_button = QPushButton("清空输入", self)
        self.clear_button.setObjectName("secondary")
        self.clear_button.clicked.connect(self.clear_form)
        form_layout.addWidget(self.save_button, 1, 6)
        form_layout.addWidget(self.clear_button, 1, 7)
        layout.addWidget(form_box)

        table_header = QHBoxLayout()
        table_title = QLabel("当天记录")
        table_title.setStyleSheet("font-size: 15px; font-weight: 700; color: #1f2937;")
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #64748b;")
        self.delete_button = QPushButton("删除选中记录", self)
        self.delete_button.setObjectName("danger")
        self.delete_button.clicked.connect(self.delete_selected_record)
        table_header.addWidget(table_title)
        table_header.addWidget(self.status_label)
        table_header.addStretch(1)
        table_header.addWidget(self.delete_button)
        layout.addLayout(table_header)

        self.table = QTableWidget(0, len(self.HEADERS), self)
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self.load_selected_record_into_form)
        layout.addWidget(self.table, stretch=1)
        self.setCentralWidget(root)

    @staticmethod
    def _amount_spin(decimals: int, maximum: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setDecimals(decimals)
        spin.setRange(0.0, maximum)
        spin.setSingleStep(0.01)
        return spin

    def selected_date_text(self) -> str:
        return self.date_edit.date().toString("yyyy-MM-dd")

    def load_selected_date(self) -> None:
        self.editing_index = None
        self.records = self.store.load(self.selected_date_text())
        self.clear_form()
        self.refresh_view()
        if self.store.last_error:
            self.status_label.setText(self.store.last_error)
            self.status_label.setStyleSheet("color: #b91c1c;")

    def refresh_view(self) -> None:
        summary = calculate_day_summary(self.records)
        for key, value in summary.items():
            self.summary_labels[key].setText(f"¥{value:,.2f}")
        net_profit = summary["net_profit"]
        net_color = "#15803d" if net_profit >= 0 else "#b91c1c"
        self.summary_labels["net_profit"].setStyleSheet(
            f"font-size: 19px; font-weight: 700; color: {net_color};"
        )

        self.table.setRowCount(len(self.records))
        for row_index, record in enumerate(self.records):
            values = [
                record.get("date", self.selected_date_text()),
                record.get("instrument_type", ""),
                record.get("direction", ""),
                record.get("code", ""),
                f"{float(record.get('price', 0.0)):.6f}",
                str(int(record.get("quantity", 0))),
                f"{trade_gross_amount(record):,.2f}",
                f"{float(record.get('fee', 0.0)):,.2f}",
                record.get("note", ""),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column in {4, 5, 6, 7}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if column == 2:
                    item.setForeground(QColor("#b91c1c") if value == "买入" else QColor("#15803d"))
                self.table.setItem(row_index, column, item)
        self.status_label.setText(f"{len(self.records)} 条记录，数据保存于 {self.store.data_dir}")
        self.status_label.setStyleSheet("color: #64748b;")

    def _record_from_form(self) -> dict[str, Any] | None:
        code = self.code_edit.text().strip().upper()
        if not code:
            QMessageBox.warning(self, APP_NAME, "请填写交易代码。")
            return None
        if self.price_spin.value() <= 0:
            QMessageBox.warning(self, APP_NAME, "价格必须大于 0。")
            return None
        return normalize_record(
            {
                "instrument_type": self.instrument_combo.currentText(),
                "direction": self.direction_combo.currentText(),
                "code": code,
                "price": self.price_spin.value(),
                "quantity": self.quantity_spin.value(),
                "fee": self.fee_spin.value(),
                "note": self.note_edit.text(),
            },
            self.selected_date_text(),
        )

    def save_form_record(self) -> None:
        record = self._record_from_form()
        if record is None:
            return
        if self.editing_index is None:
            self.records.append(record)
        else:
            self.records[self.editing_index] = record
        self._persist_and_refresh()

    def delete_selected_record(self) -> None:
        if self.editing_index is None:
            QMessageBox.information(self, APP_NAME, "请先选中一条记录。")
            return
        del self.records[self.editing_index]
        self._persist_and_refresh()

    def load_selected_record_into_form(self) -> None:
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return
        self.editing_index = selected_rows[0].row()
        record = self.records[self.editing_index]
        self.instrument_combo.setCurrentText(str(record.get("instrument_type", "现货")))
        self.direction_combo.setCurrentText(str(record.get("direction", "买入")))
        self.code_edit.setText(str(record.get("code", "")))
        self.price_spin.setValue(float(record.get("price", 0.0)))
        self.quantity_spin.setValue(max(1, int(record.get("quantity", 1))))
        self.fee_spin.setValue(float(record.get("fee", 0.0)))
        self.note_edit.setText(str(record.get("note", "")))
        self.save_button.setText("保存修改")

    def clear_form(self) -> None:
        self.editing_index = None
        self.table.clearSelection()
        self.instrument_combo.setCurrentText("现货")
        self.direction_combo.setCurrentText("买入")
        self.code_edit.clear()
        self.price_spin.setValue(0.0)
        self.quantity_spin.setValue(1)
        self.fee_spin.setValue(0.0)
        self.note_edit.clear()
        self.save_button.setText("新增记录")

    def _persist_and_refresh(self) -> None:
        try:
            self.store.save(self.selected_date_text(), self.records)
        except OSError:
            QMessageBox.critical(self, APP_NAME, self.store.last_error or "保存账本失败。")
            return
        self.clear_form()
        self.refresh_view()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    window = LedgerWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
