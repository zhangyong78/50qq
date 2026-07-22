import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication

from option_arbitrage_scanner import MainWindow


class PostMarketLedgerEntryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

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


if __name__ == "__main__":
    unittest.main()
