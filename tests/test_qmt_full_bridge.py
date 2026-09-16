import importlib.util
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock


BRIDGE = Path(__file__).resolve().parents[1] / "qmt_full_bridge_probe.py"
CALL = "10000001.SHO"
PUT = "10000002.SHO"
SPOT = "510050.SH"


def quote(bid=0.1, ask=0.101, timestamp=None):
    return {"time": int(time.time() * 1000) if timestamp is None else timestamp,
            "bidPrice": [bid], "askPrice": [ask], "lastPrice": bid}


class FullQmtStrategyTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("bridge_test", BRIDGE)
        self.bridge = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.bridge)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.bridge.g.output_file = str(Path(self.temp.name) / "bridge.json")
        self.bridge.g.temp_file = self.bridge.g.output_file + ".tmp"
        self.context = Mock()
        self.context.subscribe_whole_quote.return_value = 8
        self.context.subscribe_quote.return_value = 11
        self.context.get_full_tick.return_value = {SPOT: quote(3, 3.001)}

    def test_initial_callback_is_not_dropped_and_uses_explicit_contracts(self):
        def immediate(codes, callback):
            if codes == [CALL, PUT]:
                callback({"SHO.10000001": quote(), PUT: [quote(0.12, 0.13)]})
            return 8

        self.context.subscribe_whole_quote.side_effect = immediate
        self.bridge._replace_option_subscriptions(self.context, {CALL, PUT})
        self.bridge._poll_quotes(self.context, True)
        self.assertIn(CALL, self.bridge.g.latest_ticks)
        self.assertIn(PUT, self.bridge.g.latest_ticks)
        self.context.subscribe_quote.assert_not_called()
        self.assertIn(
            ([CALL, PUT],),
            [call.args for call in self.context.get_full_tick.call_args_list],
        )
        payload = json.loads(Path(self.bridge.g.output_file).read_text())
        self.assertEqual(payload["diagnostics"]["option_book_count"], 2)
        self.assertEqual(payload["diagnostics"]["whole_callbacks"], 1)
        self.assertEqual(payload["subscription"]["whole_quote_fallback_ids"], [8, 8])

    def test_missing_whole_quote_uses_tracked_tick_subscription_without_pandas(self):
        self.bridge._replace_option_subscriptions(self.context, {CALL})
        self.bridge._poll_quotes(self.context, True)
        self.assertEqual(self.bridge.g.option_subscription_ids, {CALL: 11})
        self.assertNotIn(CALL, self.bridge.g.latest_ticks)
        self.assertFalse(hasattr(self.context, "get_market_data_ex") and self.context.get_market_data_ex.called)
        self.bridge._poll_quotes(self.context, True)
        self.assertEqual(self.context.subscribe_quote.call_count, 1)

    def test_final_quote_falls_back_to_daily_close_without_creating_a_fake_book(self):
        self.context.get_market_data.return_value = 0.123
        self.bridge._replace_option_subscriptions(self.context, {CALL})
        self.bridge._poll_quotes(self.context, True)
        self.assertEqual(self.bridge.g.latest_ticks[CALL]["lastPrice"], 0.123)
        self.assertFalse(self.bridge._has_book(self.bridge.g.latest_ticks[CALL]))
        payload = json.loads(Path(self.bridge.g.output_file).read_text())
        self.assertEqual(payload["diagnostics"]["option_quote_count"], 1)
        self.assertEqual(payload["diagnostics"]["option_book_count"], 0)
        self.assertEqual(payload["diagnostics"]["final_quote_keys"], [CALL])

    def test_final_quote_does_not_turn_a_quote_record_into_a_fake_book(self):
        self.context.get_market_data.return_value = {
            "20260916150000000": quote(0.12, 0.13)}
        self.bridge._replace_option_subscriptions(self.context, {CALL})
        self.bridge._poll_quotes(self.context, True)
        self.assertEqual(self.bridge.g.latest_ticks[CALL]["lastPrice"], 0.12)
        self.assertFalse(self.bridge._has_book(self.bridge.g.latest_ticks[CALL]))

    def test_old_cache_and_timestamp_only_data_do_not_become_current_quotes(self):
        self.bridge.g.option_codes = {CALL}
        self.bridge._merge_ticks(
            {CALL: quote(timestamp=int((time.time() - 86400) * 1000))},
            from_cache=True,
        )
        self.assertNotIn(CALL, self.bridge.g.latest_ticks)
        self.assertEqual(self.bridge.g.cache_rejected, 1)
        self.assertFalse(self.bridge._merge_ticks({CALL: {"time": int(time.time() * 1000)}}))

    def test_runtime_errors_are_visible_in_snapshot(self):
        self.context.subscribe_whole_quote.side_effect = RuntimeError("whole denied")
        self.context.get_full_tick.side_effect = RuntimeError("full tick unavailable")
        self.bridge._replace_option_subscriptions(self.context, {CALL})
        self.bridge._poll_quotes(self.context, True)
        payload = json.loads(Path(self.bridge.g.output_file).read_text())
        self.assertEqual(payload["diagnostics"]["option_quote_count"], 0)
        self.assertIn("whole denied", payload["diagnostics"]["errors"]["whole_quote_subscribe"])
        self.assertIn("full tick unavailable", payload["diagnostics"]["errors"]["option_full_tick"])

    def test_rollover_unsubscribes_old_ids_and_removes_obsolete_ticks(self):
        self.bridge._replace_option_subscriptions(self.context, {CALL})
        self.bridge._poll_quotes(self.context, True)
        self.bridge._merge_ticks({CALL: quote()})
        self.bridge._replace_option_subscriptions(self.context, {PUT})
        self.assertEqual({c.args[0] for c in self.context.unsubscribe_quote.call_args_list}, {8, 11})
        self.assertNotIn(CALL, self.bridge.g.latest_ticks)
        self.assertIn(SPOT, self.bridge.g.latest_ticks)
        self.assertFalse(self.bridge._merge_ticks({CALL: quote()}))
        self.assertTrue(self.bridge._merge_ticks({"10000002.SH": quote()}))
        self.assertIn(PUT, self.bridge.g.latest_ticks)

    def test_nearest_unexpired_month_changes_without_editing_script(self):
        calls = [CALL, "10000003.SHO"]
        puts = [PUT, "10000004.SHO"]
        self.context.get_option_list.side_effect = lambda spot, day, side, available: calls if side == "CALL" else puts
        self.context.get_option_detail_data.side_effect = lambda code: {
            "OptExercisePrice": 3.0,
            "ExpireDate": "20260923" if code in (CALL, PUT) else "20261028"}
        self.bridge.g.latest_ticks[SPOT] = quote(3, 3.001)
        before = self.bridge._underlying_pairs(self.context, "50ETF", SPOT, "20260916")
        after = self.bridge._underlying_pairs(self.context, "50ETF", SPOT, "20260924")
        self.assertEqual(before[0]["expiry"], "2026-09-23")
        self.assertEqual(after[0]["expiry"], "2026-10-28")
        self.assertEqual(after[0]["call_code"], "10000003.SHO")


if __name__ == "__main__":
    unittest.main()
