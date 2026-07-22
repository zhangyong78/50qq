import unittest
from unittest.mock import patch

from option_arbitrage_scanner import (
    current_expiry_yyyymm,
    option_moneyness_text,
    pick_atm_for_underlying,
    recommendation_effective_profit,
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
        self.assertEqual(option_moneyness_text(3.075, 3.10, is_call=False), "现价低于行权价")
        self.assertEqual(option_moneyness_text(3.075, 3.00, is_call=True), "现价高于行权价")
        self.assertEqual(option_moneyness_text(3.075, 3.0754, is_call=True), "现价接近行权价")

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
