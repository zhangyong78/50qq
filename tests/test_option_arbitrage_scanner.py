import unittest
from unittest.mock import patch

from option_arbitrage_scanner import (
    current_expiry_yyyymm,
    option_moneyness_text,
    pick_atm_for_underlying,
    recommendation_effective_profit,
    sort_mode_rows_by_strike,
)


class ExpiryAndMoneynessTests(unittest.TestCase):
    @patch("option_arbitrage_scanner.time.strftime", return_value="202607")
    def test_current_expiry_month_uses_calendar_month(self, _strftime):
        self.assertEqual(current_expiry_yyyymm(), "202607")

    @patch("option_arbitrage_scanner._gather_option_strike_pairs")
    @patch("option_arbitrage_scanner.run_with_timeout", return_value=(None, None))
    @patch("option_arbitrage_scanner.time.strftime", return_value="202607")
    def test_atm_lookup_does_not_retry_all_expiries(self, _strftime, _timeout, gather_pairs):
        gather_pairs.return_value = ({}, {}, {})

        self.assertIsNone(pick_atm_for_underlying("510050.SH", 3.075, "202607"))
        self.assertEqual(len(gather_pairs.call_args_list), 1)
        self.assertEqual(gather_pairs.call_args_list[0].args[2], "202607")

    def test_display_uses_direct_price_relation(self):
        self.assertEqual(option_moneyness_text(3.075, 3.10, is_call=False), "行权价高于现价")
        self.assertEqual(option_moneyness_text(3.075, 3.00, is_call=True), "行权价低于现价")
        self.assertEqual(option_moneyness_text(3.075, 3.0754, is_call=True), "行权价接近现价")

    def test_mode_rows_sort_by_numeric_strike_then_option_code(self):
        rows = [
            {"strike": 3.20, "option_code": "B.SH"},
            {"strike": 3.00, "option_code": "C.SH"},
            {"strike": 3.20, "option_code": "A.SH"},
        ]

        self.assertEqual(
            [row["option_code"] for row in sort_mode_rows_by_strike(rows)],
            ["C.SH", "A.SH", "B.SH"],
        )

    def test_conditional_recommendation_uses_boolean_not_display_text(self):
        row = {
            "profit": -21.10,
            "alert_eligible": False,
            "is_in_the_money": True,
            "moneyness_text": "现价低于行权价",
            "exercise_upper_profit": 39.95,
        }

        self.assertEqual(recommendation_effective_profit(row), 39.95)


if __name__ == "__main__":
    unittest.main()
