import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication

from option_arbitrage_scanner import (
    ConfigDialog,
    FeeConfig,
    MainWindow,
    MODE_TIME_VALUE_REQUIREMENTS,
    OptionPair,
    Tick,
    build_market_status,
    ticks_with_last_price_estimates,
    current_expiry_yyyymm,
    default_app_config,
    default_fee_config,
    calculate_opportunities,
    load_app_config,
    format_worker_status_message,
    ARBITRAGE_MODE_DEFS,
    FullQmtBridgeSource,
    option_exercise_status_text,
    option_moneyness_text,
    pick_atm_for_underlying,
    recommendation_effective_profit,
    recommendation_guidance_html,
    recommendation_guidance_text,
    strike_distance_tier,
    is_option_quote_session,
    sort_mode_rows_by_strike,
)


class ExpiryAndMoneynessTests(unittest.TestCase):
    def test_exercise_fees_apply_to_the_corresponding_outcomes(self):
        pair = OptionPair("50ETF", "spot", 3.0, "call", "put")
        ticks = {"spot": Tick(2.99, 3.01, 3.0), "call": Tick(0.1, 0.11, 0.105), "put": Tick(0.1, 0.11, 0.105)}
        data = default_fee_config()
        rows = {r["mode_key"]: r for r in calculate_opportunities([pair], ticks, FeeConfig.from_dict(data))}
        data.update(option_exercise_fee=0.0, option_passive_exercise_fee=0.0)
        without_fees = {r["mode_key"]: r for r in calculate_opportunities([pair], ticks, FeeConfig.from_dict(data))}
        for mode in ("模式1", "模式4"):
            self.assertAlmostEqual(without_fees[mode]["profit"] - rows[mode]["profit"], 0.7)
        for mode in ("模式2", "模式3"):
            self.assertAlmostEqual(without_fees[mode]["exercise_upper_profit"] - rows[mode]["exercise_upper_profit"], 0.1)
            self.assertEqual(without_fees[mode]["profit"], rows[mode]["profit"])
            rows[mode]["is_in_the_money"] = True
            formula = MainWindow._recommendation_formula_text(SimpleNamespace(fees=FeeConfig.from_dict(default_fee_config())), rows[mode])
            self.assertIn("- 0.10", formula)

    def test_legacy_fee_configuration_is_upgraded_but_custom_values_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({"fees": {"option_exercise_fee": 4.0}}), encoding="utf-8")
            self.assertEqual(load_app_config(path)["fees"]["option_exercise_fee"], 0.7)
            path.write_text(json.dumps({"fees": {"option_exercise_fee": 4.0, "option_passive_exercise_fee": 0.2}}), encoding="utf-8")
            self.assertEqual(load_app_config(path)["fees"]["option_exercise_fee"], 4.0)

    def test_quote_session_excludes_after_close_and_weekends(self):
        self.assertTrue(is_option_quote_session(1789524600.0))  # 2026-09-16 10:10 Shanghai
        self.assertFalse(is_option_quote_session(1789557000.0))  # 2026-09-16 19:10 Shanghai
        self.assertFalse(is_option_quote_session(1789870200.0))  # 2026-09-20 Sunday 10:10 Shanghai

    def test_full_qmt_bridge_reads_pair_metadata_and_bid_ask(self):
        payload = {
            "type": "full_qmt_bridge",
            "ticks": {
                "510050.SH": {"bidPrice": [2.999], "askPrice": [3.001], "lastPrice": 3.0},
                "10000001.SHO": {"bidPrice": [0.102], "askPrice": [0.103]},
                "10000002.SHO": {"bidPrice": [0.101], "askPrice": [0.102]},
                "10000003.SHO": {"lastPrice": 0.11},
                "10000004.SHO": {"bidPrice": [0.11], "lastPrice": 0.11},
            },
            "pairs": [
                {
                    "pool_name": "50ETF",
                    "spot_code": "510050.SH",
                    "strike": 3.0,
                    "call_code": "10000001.SHO",
                    "put_code": "10000002.SHO",
                    "expiry": "2026-09-23",
                    "atm_tier": 0,
                    "ref_atm_strike": 3.0,
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            bridge_file = Path(directory) / "bridge.json"
            bridge_file.write_text(json.dumps(payload), encoding="utf-8")
            pairs, ticks, message = FullQmtBridgeSource(str(bridge_file)).fetch_snapshot()

        self.assertEqual(message["type"], "full_qmt_bridge")
        self.assertEqual(pairs[0].call_code, "10000001.SHO")
        self.assertEqual(pairs[0].atm_tier, 0)
        self.assertEqual(ticks["510050.SH"], Tick(2.999, 3.001, 3.0))
        self.assertNotIn("10000003.SHO", ticks)
        self.assertNotIn("10000004.SHO", ticks)
        self.assertEqual(message["_last_only_prices"]["10000003.SHO"], 0.11)

    def test_market_status_keeps_last_price_separate_from_executable_book(self):
        pair = OptionPair(
            pool_name="50ETF", spot_code="510050.SH", strike=3.0,
            call_code="10000001.SHO", put_code="10000002.SHO", expiry="2026-09-23",
        )
        status = build_market_status(
            [pair], [pair], {"510050.SH": Tick(2.999, 3.001, 3.0)},
            last_only_prices={"10000001.SHO": 0.123},
        )
        self.assertEqual(status["option_ok"], 0)
        self.assertEqual(status["option_last_only"], 1)
        self.assertEqual(status["contracts"]["510050.SH"]["call_last"], 0.123)

    def test_last_prices_can_feed_display_only_calculation_ticks(self):
        estimated = ticks_with_last_price_estimates(
            {"510050.SH": Tick(2.999, 3.001, 3.0)},
            {"10000001.SHO": 0.123},
        )
        self.assertEqual(estimated["10000001.SHO"], Tick(0.123, 0.123, 0.123))
        self.assertEqual(estimated["510050.SH"], Tick(2.999, 3.001, 3.0))

    def test_worker_status_reports_last_prices_without_claiming_a_book(self):
        pair = OptionPair(
            pool_name="50ETF", spot_code="510050.SH", strike=3.0,
            call_code="10000001.SHO", put_code="10000002.SHO", expiry="2026-09-23",
        )
        message, connected = format_worker_status_message(
            connected=True, use_mock=False, connect_note="收盘后快照", pairs=[pair], ticks={},
            last_only_prices={"10000001.SHO": 0.123, "10000002.SHO": 0.101},
        )
        self.assertFalse(connected)
        self.assertIn("已读取 2/2 张期权末价", message)
        self.assertIn("等待买一/卖一盘口", message)

    def test_mode_titles_show_expected_time_value_direction(self):
        self.assertEqual(MODE_TIME_VALUE_REQUIREMENTS["模式1"], "时间价值需为负数")
        self.assertEqual(MODE_TIME_VALUE_REQUIREMENTS["模式4"], "时间价值需为负数")
        self.assertEqual(MODE_TIME_VALUE_REQUIREMENTS["模式2"], "时间价值需为正数")
        self.assertEqual(MODE_TIME_VALUE_REQUIREMENTS["模式3"], "时间价值需为正数")

    def test_default_stock_commission_is_one_basis_point(self):
        self.assertEqual(default_fee_config()["stock_commission_rate"], 0.0001)

    def test_recommendation_guidance_contains_time_value_rules(self):
        guidance = recommendation_guidance_text([])
        self.assertIn("买入认沽/买入认购（模式1、4）通常优先选择时间价值为负", guidance)
        self.assertIn("卖出认沽/卖出认购（模式2、3）通常优先选择时间价值为正", guidance)

    def test_recommendation_guidance_flags_high_active_call_return(self):
        guidance = recommendation_guidance_text(
            [
                {
                    "mode_key": "模式4",
                    "is_in_the_money": True,
                    "time_value": -0.005,
                    "profit": 72.35,
                }
            ]
        )
        self.assertIn("模式4买入认购主动行权口径约 72.35 元/张", guidance)
        self.assertIn("优先核对主动行权条件", guidance)

    def test_recommendation_guidance_marks_active_exercise_lines_red(self):
        guidance_html = recommendation_guidance_html([])
        self.assertIn('color:#b91c1c;font-weight:600;', guidance_html)
        self.assertIn("主动行权提示", guidance_html)

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


class ConfigDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def test_config_dialog_constructs_with_quote_source_selector(self):
        dialog = ConfigDialog(default_app_config())
        self.assertEqual(dialog.quote_source_combo.count(), 2)
        self.assertEqual(dialog.quote_source_combo.currentData(), "qmt_api")
        dialog.close()

    def test_exercise_fees_can_be_configured_and_saved(self):
        dialog = ConfigDialog(default_app_config())
        self.assertEqual(dialog.option_exercise_fee_spin.value(), 0.7)
        self.assertEqual(dialog.option_passive_exercise_fee_spin.value(), 0.1)
        dialog.option_exercise_fee_spin.setValue(1.2)
        dialog.option_passive_exercise_fee_spin.setValue(0.3)
        fees = dialog.to_config()["fees"]
        self.assertEqual(fees["option_exercise_fee"], 1.2)
        self.assertEqual(fees["option_passive_exercise_fee"], 0.3)
        dialog.close()


if __name__ == "__main__":
    unittest.main()
