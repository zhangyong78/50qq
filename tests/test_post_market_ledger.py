import tempfile
import unittest
from pathlib import Path

from post_market_ledger import (
    StrategyLedgerStore,
    calculate_settled_profit,
    format_settlement_formula,
    validate_settlement_record,
)


class SettlementCalculationTests(unittest.TestCase):
    def test_mode1_active_put_settlement_charges_buy_and_exercise_fees(self):
        record = {
            "mode": "mode1",
            "strike": 3.10,
            "stock_shares": 10000,
            "stock_price": 3.05,
            "option_contracts": 1,
            "option_premium": 50.0,
            "stock_commission_rate": 0.0002,
            "option_buy_open_fee": 2.0,
            "active_exercise_fee": 4.0,
        }

        self.assertEqual(calculate_settled_profit(record), 437.90)

    def test_mode2_passive_put_assignment_matches_manual_example(self):
        record = {
            "mode": "mode2",
            "strike": 3.10,
            "stock_shares": 60000,
            "stock_price": 3.09,
            "option_contracts": 6,
            "option_premium": 201.0,
            "stock_commission_rate": 0.0002,
        }

        self.assertEqual(calculate_settled_profit(record), 568.92)

    def test_mode3_passive_call_assignment_does_not_charge_option_fees(self):
        record = {
            "mode": "mode3",
            "strike": 3.10,
            "stock_shares": 10000,
            "stock_price": 3.05,
            "option_contracts": 1,
            "option_premium": 50.0,
            "stock_commission_rate": 0.0002,
            "option_buy_open_fee": 999.0,
            "active_exercise_fee": 999.0,
        }

        self.assertEqual(calculate_settled_profit(record), 543.90)

    def test_mode4_active_call_settlement_includes_borrow_and_option_fees(self):
        record = {
            "mode": "mode4",
            "strike": 3.10,
            "stock_shares": 10000,
            "stock_price": 3.15,
            "option_contracts": 1,
            "option_premium": 50.0,
            "stock_commission_rate": 0.0002,
            "option_buy_open_fee": 2.0,
            "active_exercise_fee": 4.0,
            "borrow_cost": 10.0,
        }

        self.assertEqual(calculate_settled_profit(record), 427.70)

    def test_rejects_stock_option_quantity_mismatch(self):
        with self.assertRaisesRegex(ValueError, "10000"):
            validate_settlement_record(
                {
                    "mode": "mode2",
                    "strike": 3.10,
                    "stock_shares": 10000,
                    "stock_price": 3.09,
                    "option_contracts": 2,
                    "option_premium": 201.0,
                }
            )

    def test_formula_text_contains_substituted_result(self):
        record = {
            "mode": "mode2",
            "strike": 3.10,
            "stock_shares": 60000,
            "stock_price": 3.09,
            "option_contracts": 6,
            "option_premium": 201.0,
            "stock_commission_rate": 0.0002,
        }

        formula = format_settlement_formula(record)

        self.assertIn("3.0900", formula)
        self.assertIn("568.92", formula)


class StrategyLedgerStoreTests(unittest.TestCase):
    def test_store_round_trips_one_month(self):
        records = [{"id": "one", "result": 568.92}]
        with tempfile.TemporaryDirectory() as temp_dir:
            store = StrategyLedgerStore(Path(temp_dir))
            store.save("2026-07", records)

            self.assertEqual(store.load("2026-07"), records)

    def test_store_rejects_invalid_month(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = StrategyLedgerStore(Path(temp_dir))
            with self.assertRaisesRegex(ValueError, "YYYY-MM"):
                store.load("2026-7")


if __name__ == "__main__":
    unittest.main()

