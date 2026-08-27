import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication, QTableWidgetItem

from option_arbitrage_scanner import APP_VERSION, APP_WINDOW_TITLE, MainWindow


class PostMarketLedgerEntryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def test_window_title_includes_release_version(self):
        self.assertEqual(APP_VERSION, "V2026.08.28")
        self.assertEqual(APP_WINDOW_TITLE, "A股ETF期权交割套利机会扫描器 V2026.08.28")

    @patch("option_arbitrage_scanner.StrategyLedgerDialog")
    @patch.object(MainWindow, "_start_worker")
    def test_post_market_entry_opens_ledger_beside_config(self, _start_worker, dialog_class):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "contracts_config.json"
            window = MainWindow(config_path)

            window.open_post_market_ledger()

            dialog_class.assert_called_once_with(Path(temp_dir), window)
            dialog_class.return_value.exec.assert_called_once_with()
            window.close()

    @patch.object(MainWindow, "_start_worker")
    def test_selected_mode2_row_maps_bid_prices_to_ledger_prefill(self, _start_worker):
        with tempfile.TemporaryDirectory() as temp_dir:
            window = MainWindow(Path(temp_dir) / "contracts_config.json")
            table = window.mode_tables["模式2"]
            window.rendered_rows_by_mode["模式2"] = [
                {
                    "pool": "50ETF",
                    "option_code": "10011695.SH",
                    "strike": 3.10,
                    "spot_bid": 3.09,
                    "spot_ask": 3.10,
                    "option_bid": 0.0201,
                    "option_ask": 0.0205,
                }
            ]
            table.setRowCount(1)
            table.setItem(0, 0, QTableWidgetItem("50ETF"))
            table.selectRow(0)

            self.assertEqual(
                window._selected_ledger_prefill(),
                {
                    "mode": "mode2",
                    "etf_code": "50ETF",
                    "option_code": "10011695.SH",
                    "strike": 3.10,
                    "stock_price": 3.09,
                    "option_premium": 201.0,
                    "stock_shares": 10000,
                    "option_contracts": 1,
                },
            )
            window.close()

    @patch("option_arbitrage_scanner.StrategyLedgerDialog")
    @patch.object(MainWindow, "_selected_ledger_prefill")
    @patch.object(MainWindow, "_start_worker")
    def test_selected_row_is_applied_before_ledger_opens(
        self,
        _start_worker,
        selected_prefill,
        dialog_class,
    ):
        prefill = {"mode": "mode2", "etf_code": "510050"}
        selected_prefill.return_value = prefill
        with tempfile.TemporaryDirectory() as temp_dir:
            window = MainWindow(Path(temp_dir) / "contracts_config.json")

            window.open_post_market_ledger()

            dialog_class.return_value.apply_prefill.assert_called_once_with(prefill)
            dialog_class.return_value.exec.assert_called_once_with()
            window.close()


if __name__ == "__main__":
    unittest.main()
