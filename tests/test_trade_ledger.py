import tempfile
import unittest
from pathlib import Path

from trade_ledger import LedgerStore, calculate_day_summary, trade_gross_amount


class TradeLedgerTests(unittest.TestCase):
    def test_trade_amount_uses_spot_and_option_multipliers(self):
        self.assertEqual(
            trade_gross_amount({"instrument_type": "现货", "price": 3.02, "quantity": 10000}),
            30200.0,
        )
        self.assertEqual(
            trade_gross_amount({"instrument_type": "期权", "price": 0.0215, "quantity": 2}),
            430.0,
        )

    def test_daily_summary_uses_cash_flow_minus_fees(self):
        records = [
            {"instrument_type": "现货", "direction": "买入", "price": 3.02, "quantity": 10000, "fee": 6.04},
            {"instrument_type": "期权", "direction": "卖出", "price": 0.0215, "quantity": 2, "fee": 0.0},
        ]

        self.assertEqual(
            calculate_day_summary(records),
            {
                "buy_amount": 30200.0,
                "sell_amount": 430.0,
                "fee_amount": 6.04,
                "net_profit": -29776.04,
            },
        )

    def test_store_saves_and_loads_one_day(self):
        records = [{"code": "510050.SH", "direction": "买入"}]
        with tempfile.TemporaryDirectory() as temp_dir:
            store = LedgerStore(Path(temp_dir))
            store.save("2026-07-22", records)
            self.assertEqual(store.load("2026-07-22"), records)


if __name__ == "__main__":
    unittest.main()
