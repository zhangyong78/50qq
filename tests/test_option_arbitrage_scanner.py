import unittest
from unittest.mock import patch

from option_arbitrage_scanner import (
    MainWindow,
    OptionPair,
    Tick,
    build_market_status,
    current_expiry_yyyymm,
    option_exercise_status_text,
    option_moneyness_text,
    pick_atm_for_underlying,
    recommendation_effective_profit,
    strike_distance_tier,
    sort_mode_rows_by_strike,
)


class ExpiryAndMoneynessTests(unittest.TestCase):
    def test_profit_column_explicitly_states_unexercised_assumption(self):
        self.assertEqual(MainWindow.MODE_TABLE_HEADERS[4], "未被行权每张收益(元)")

    def test_exercise_status_column_follows_current_status_column(self):
        self.assertEqual(MainWindow.MODE_TABLE_HEADERS[7], "当前状态")
        self.assertEqual(MainWindow.MODE_TABLE_HEADERS[8], "当前行权判断")
        self.assertEqual(MainWindow._TIME_VALUE_COLUMN, 14)

    def test_quote_columns_are_split_into_three_color_groups(self):
        styles = MainWindow._QUOTE_COLUMN_GROUP_STYLES
        self.assertEqual(styles[9], styles[10])
        self.assertEqual(styles[11], styles[12])
        self.assertEqual(styles[13], styles[14])
        self.assertEqual(len({styles[9], styles[11], styles[13]}), 3)

    def test_exercise_status_uses_severity_based_alert_colors(self):
        self.assertEqual(
            MainWindow._exercise_status_alert_style("买入认沽：实值；需主动行权卖出现货"),
            ("#d90429", "#ffffff"),
        )
        self.assertEqual(
            MainWindow._exercise_status_alert_style("卖出认沽：实值；可能被行权接货"),
            ("#ffe66d", "#7a4300"),
        )
        self.assertIsNone(MainWindow._exercise_status_alert_style("卖出认购：虚值；通常不行权"))

    def test_exercise_status_explains_direction_and_expiry_outcome(self):
        self.assertEqual(
            option_exercise_status_text(3.0865, 3.10, is_call=True, is_long_option=False),
            "卖出认购：虚值；若到期维持，通常不行权",
        )
        self.assertEqual(
            option_exercise_status_text(3.0865, 3.10, is_call=False, is_long_option=False),
            "卖出认沽：实值；若到期维持，可能被行权接货",
        )
        self.assertEqual(
            option_exercise_status_text(3.10, 3.10, is_call=True, is_long_option=False),
            "卖出认购：近平值；到期是否行权取决于结算价",
        )
        self.assertEqual(
            option_exercise_status_text(3.0865, 3.10, is_call=False, is_long_option=True),
            "买入认沽：实值；若到期维持，需主动行权卖出现货",
        )
        self.assertEqual(
            option_exercise_status_text(3.0865, 3.10, is_call=True, is_long_option=True),
            "买入认购：虚值；若到期维持，通常无需主动行权",
        )
        self.assertEqual(
            option_exercise_status_text(3.20, 3.10, is_call=True, is_long_option=True),
            "买入认购：实值；若到期维持，需主动行权买入现货回补",
        )

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

    def test_market_status_keeps_atm_pair_when_ladder_has_multiple_tiers(self):
        atm = OptionPair(
            "50ETF",
            "510050.SH",
            2.75,
            "CALL_ATM",
            "PUT_ATM",
            "2026-08-26",
            atm_tier=0,
            ref_atm_strike=2.75,
        )
        outer = OptionPair(
            "50ETF",
            "510050.SH",
            3.00,
            "CALL_OUTER",
            "PUT_OUTER",
            "2026-08-26",
            atm_tier=5,
            ref_atm_strike=2.75,
        )
        status = build_market_status(
            [atm],
            [atm, outer],
            {
                "510050.SH": Tick(2.74, 2.76, 2.75),
                "CALL_ATM": Tick(0.1, 0.2, 0.15),
                "PUT_ATM": Tick(0.1, 0.2, 0.15),
                "CALL_OUTER": Tick(0.1, 0.2, 0.15),
                "PUT_OUTER": Tick(0.1, 0.2, 0.15),
            },
        )

        self.assertEqual(status["contracts"]["510050.SH"]["strike"], 2.75)
        self.assertEqual(status["spots"]["510050.SH"]["price"], 2.75)
        self.assertEqual(status["option_total"], 4)

    def test_strike_tier_uses_actual_listed_strike_positions(self):
        self.assertEqual(
            strike_distance_tier(5.0, 4.8, "510300.SH", [4.8, 4.9, 5.0]),
            2,
        )
        self.assertEqual(
            strike_distance_tier(8.25, 8.0, "510500.SH", [8.0, 8.25, 8.5]),
            1,
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
