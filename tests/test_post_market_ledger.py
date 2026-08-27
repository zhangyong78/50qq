import tempfile
import unittest
from pathlib import Path

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import QApplication, QLabel

from post_market_ledger import (
    StrategyLedgerDialog,
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
    def test_store_round_trips_all_records_in_one_config_side_file(self):
        records = [
            {"id": "june", "settlement_date": "2026-06-24", "result": 568.92},
            {"id": "july", "settlement_date": "2026-07-22", "result": 437.90},
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            store = StrategyLedgerStore(Path(temp_dir))
            store.save_all(records)

            self.assertEqual(store.data_path, Path(temp_dir) / "strategy_ledger.json")
            self.assertEqual(store.load_all(), records)


class StrategyLedgerDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def test_dialog_shows_all_records_while_month_is_used_for_data_entry(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir)
            StrategyLedgerStore(config_dir).save_all(
                [
                    {"id": "june", "settlement_date": "2026-06-24", "result": 10.0},
                    {"id": "july", "settlement_date": "2026-07-22", "result": 20.0},
                ]
            )
            dialog = StrategyLedgerDialog(config_dir)
            dialog.month_edit.setDate(QDate(2026, 7, 1))

            self.assertEqual(dialog.store.data_path, config_dir / "strategy_ledger.json")
            self.assertEqual(dialog.table.rowCount(), 2)
            self.assertTrue(dialog.month_total_label.text().startswith("账本累计"))
            self.assertEqual(dialog.settlement_date_edit.date().toString("yyyy-MM"), "2026-07")

    def test_form_defaults_and_auto_stock_shares_follow_contracts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dialog = StrategyLedgerDialog(Path(temp_dir))
            dialog.option_contracts_spin.setValue(3)

            self.assertEqual(dialog.stock_shares, 30000)
            self.assertEqual(dialog.strike_spin.value(), 1.0)
            self.assertEqual(dialog.stock_price_spin.value(), 1.0)
            self.assertEqual(dialog.option_premium_spin.value(), 1.0)
            self.assertEqual(dialog.stock_commission_rate, 0.0001)
            self.assertEqual(dialog.option_buy_open_fee, 1.7)
            self.assertEqual(dialog.active_exercise_fee, 4.0)
            self.assertFalse(
                any("融券/资金成本" in label.text() for label in dialog.findChildren(QLabel))
            )

    def test_passive_mode_does_not_charge_option_open_and_exercise_fees(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dialog = StrategyLedgerDialog(Path(temp_dir))
            dialog.mode_combo.setCurrentIndex(1)
            record = dialog._record_from_form()

            self.assertIsNotNone(record)
            self.assertEqual(record["option_buy_open_fee"], 0.0)
            self.assertEqual(record["active_exercise_fee"], 0.0)
            self.assertNotIn("borrow_cost", record)

    def test_form_display_precision_follows_price_direction_and_option_side(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dialog = StrategyLedgerDialog(Path(temp_dir))

            self.assertEqual(dialog.strike_spin.decimals(), 2)
            dialog.mode_combo.setCurrentIndex(1)  # mode2: sell put + sell spot
            self.assertEqual(dialog.stock_price_spin.decimals(), 3)
            self.assertEqual(dialog.option_premium_spin.decimals(), 0)

            dialog.mode_combo.setCurrentIndex(2)  # mode3: sell call + hold spot
            self.assertEqual(dialog.stock_price_spin.decimals(), 6)
            self.assertEqual(dialog.option_premium_spin.decimals(), 0)

            dialog.mode_combo.setCurrentIndex(3)  # mode4: buy call + sell spot
            self.assertEqual(dialog.stock_price_spin.decimals(), 3)
            self.assertEqual(dialog.option_premium_spin.decimals(), 2)

    def test_prefill_updates_form_without_creating_a_record(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dialog = StrategyLedgerDialog(Path(temp_dir))

            dialog.apply_prefill(
                {
                    "mode": "mode2",
                    "etf_code": "510050",
                    "option_code": "10011695.SH",
                    "strike": 3.10,
                    "stock_price": 3.09,
                    "option_premium": 201.0,
                    "stock_shares": 10000,
                    "option_contracts": 1,
                }
            )

            self.assertEqual(dialog.mode_combo.currentData(), "mode2")
            self.assertEqual(dialog.etf_code_edit.text(), "510050")
            self.assertEqual(dialog.stock_price_spin.value(), 3.09)
            self.assertEqual(dialog.option_premium_spin.value(), 201.0)
            self.assertEqual(dialog.table.rowCount(), 0)
            self.assertEqual(dialog.save_button.text(), "新增记录")


if __name__ == "__main__":
    unittest.main()
