#coding:gbk
"""Full QMT quote bridge for the ETF option scanner.

Paste this whole file into a Full-QMT Python strategy and run it in quote
simulation/live mode. It writes only selected bid/ask quotes to a local file.
"""

import json
import math
import os
import time
import _thread


class State(object):
    pass


g = State()
g.version = "2026.09.16.6"
g.output_file = r"D:\mycode\50qq\qmt_full_bridge.json"
g.temp_file = g.output_file + ".tmp"
g.spot_items = [
    ("50ETF", "510050.SH"),
    ("STAR50ETF", "588000.SH"),
    ("300ETF", "510300.SH"),
    ("500ETF", "510500.SH"),
    ("159915", "159915.SZ"),
]
g.spot_codes = [item[1] for item in g.spot_items]
g.max_tiers = 5
g.chain_refresh_sec = 300.0
g.write_interval_sec = 0.25
g.spot_subscription_id = 0
g.option_market_subscription_id = 0
g.option_market_fallback_ids = []
g.option_subscription_ids = {}
g.option_codes = set()
g.option_aliases = {}
g.pairs = []
g.latest_ticks = {}
g.subscription_failed = []
g.write_lock = _thread.allocate_lock()
g.last_write_at = 0.0
g.last_fallback_at = 0.0
g.last_local_at = 0.0
g.last_subscribe_attempt = 0.0
g.last_report_at = 0.0
g.whole_callbacks = 0
g.tick_callbacks = 0
g.last_option_received_at = 0.0
g.errors = {}
g.cache_rejected = 0
g.callback_sample = {}
g.full_tick_keys = []
g.full_tick_option_keys = []
g.final_quote_keys = []
g.last_chain_refresh_at = 0.0
g.direct_write_reported = False


def _first_number(value):
    if isinstance(value, dict):
        for item in value.values():
            number = _first_number(item)
            if number > 0:
                return number
        return 0.0
    if isinstance(value, (list, tuple)):
        if not value:
            return 0.0
        value = value[0]
    try:
        number = float(value)
        return number if math.isfinite(number) else 0.0
    except Exception:
        return 0.0


def _final_price(value):
    """Extract a closing/last value without mistaking a timestamp for price."""
    if hasattr(value, "iloc"):
        try:
            value = value.iloc[-1].to_dict()
        except Exception:
            return 0.0
    if isinstance(value, dict):
        for name in ("lastPrice", "close", "price"):
            if name in value:
                price = _first_number(value.get(name))
                if price > 0:
                    return price
        for item in reversed(list(value.values())):
            price = _final_price(item)
            if price > 0:
                return price
        return 0.0
    if isinstance(value, (list, tuple)):
        for item in reversed(value):
            price = _final_price(item)
            if price > 0:
                return price
        return 0.0
    return _first_number(value)


def _plain_value(value):
    if hasattr(value, "tolist"):
        return _plain_value(value.tolist())
    if isinstance(value, (list, tuple)):
        return [_plain_value(item) for item in value]
    if hasattr(value, "item"):
        return _plain_value(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return 0.0
    return value


def _quote_fields(tick):
    # get_market_data_ex returns DataFrames; callbacks can return tick lists.
    if hasattr(tick, "iloc"):
        if len(tick) == 0:
            return None
        tick = tick.iloc[-1].to_dict()
    elif isinstance(tick, (list, tuple)):
        tick = tick[-1] if tick else None
    if not isinstance(tick, dict):
        return None
    result = {}
    for name in (
        "time", "timetag", "stime", "lastPrice", "open", "high", "low", "lastClose",
        "amount", "volume", "bidPrice", "askPrice", "bidVol", "askVol",
    ):
        if name in tick:
            result[name] = _plain_value(tick[name])
    for side in ("bid", "ask"):
        name = side + "Price"
        if name not in result and name + "1" in tick:
            result[name] = [_first_number(tick.get(name + str(i))) for i in range(1, 6)]
    if not any(_first_number(result.get(k)) > 0 for k in ("lastPrice", "bidPrice", "askPrice")):
        return None
    return result


def _tick_day(tick):
    stamp = _first_number(tick.get("time"))
    if stamp > 100000000000:
        stamp /= 1000.0
    if 1000000000 < stamp < 10000000000:
        return time.strftime("%Y%m%d", time.localtime(stamp))
    for key in ("timetag", "stime"):
        digits = "".join(c for c in str(tick.get(key, "")) if c.isdigit())
        if len(digits) >= 8:
            return digits[:8]
    return ""


def _has_book(tick):
    return (_first_number(tick.get("bidPrice")) > 0
            and _first_number(tick.get("askPrice")) > 0)


def _merge_ticks(ticks, from_cache=False):
    selected = {}
    if isinstance(ticks, dict):
        for code, tick in ticks.items():
            code = str(code).strip().upper()
            code = g.option_aliases.get(code, code)
            if code not in g.option_codes and code not in g.spot_codes:
                continue
            fields = _quote_fields(tick)
            if fields is not None:
                day = _tick_day(fields)
                today = time.strftime("%Y%m%d")
                if (day and day != today) or (from_cache and not day):
                    g.cache_rejected += 1
                    continue
                previous = g.latest_ticks.get(code, {})
                if (_first_number(previous.get("time")) > _first_number(fields.get("time"))
                        and fields.get("time") is not None):
                    continue
                selected[code] = fields
                if code in g.option_codes:
                    g.last_option_received_at = time.time()
    if selected:
        g.latest_ticks.update(selected)
    return bool(selected)


def _write_snapshot(force=False):
    with g.write_lock:
        now = time.time()
        if not force and now - g.last_write_at < g.write_interval_sec:
            return
        message = {
            "type": "full_qmt_bridge",
            "source": "full_qmt",
            "bridge_version": g.version,
            "sent_at": int(now * 1000),
            "ticks": dict(g.latest_ticks),
            "pairs": list(g.pairs),
            "subscription": {
                "spot_codes": list(g.spot_codes),
                "option_codes": sorted(g.option_codes),
                "option_count": len(g.option_codes),
                "whole_quote_id": g.option_market_subscription_id,
                "whole_quote_fallback_ids": list(g.option_market_fallback_ids),
                "tick_subscription_count": len(g.option_subscription_ids),
                "failed": list(g.subscription_failed),
            },
            "diagnostics": {
                "option_quote_count": sum(1 for c in g.option_codes if c in g.latest_ticks),
                "option_book_count": sum(1 for c in g.option_codes if _has_book(g.latest_ticks.get(c, {}))),
                "whole_callbacks": g.whole_callbacks,
                "tick_callbacks": g.tick_callbacks,
                "last_option_received_at": g.last_option_received_at,
                "cache_rejected": g.cache_rejected,
                "callback_sample": dict(g.callback_sample),
                "full_tick_keys": list(g.full_tick_keys),
                "full_tick_option_keys": list(g.full_tick_option_keys),
                "final_quote_keys": list(g.final_quote_keys),
                "errors": dict(g.errors),
            },
        }
        try:
            with open(g.temp_file, "w") as stream:
                json.dump(message, stream, ensure_ascii=True, separators=(",", ":"))
                stream.flush()
            replace_error = None
            for attempt in range(4):
                try:
                    os.replace(g.temp_file, g.output_file)
                    g.last_write_at = now
                    return
                except Exception as exc:
                    replace_error = exc
                    if attempt < 3:
                        time.sleep(0.03)
            with open(g.output_file, "w") as stream:
                json.dump(message, stream, ensure_ascii=True, separators=(",", ":"))
                stream.flush()
            g.last_write_at = now
            if not g.direct_write_reported:
                print("bridge direct-write fallback: " + str(replace_error))
                g.direct_write_reported = True
        except Exception as exc:
            print("bridge file write failed: " + str(exc))


def _on_spot_quote(data):
    if _merge_ticks(data):
        _write_snapshot(False)


def _on_option_quote(data):
    g.tick_callbacks += 1
    _sample_callback(data)
    if _merge_ticks(data):
        _write_snapshot(False)


def _on_option_market_quote(data):
    """The requested codes are installed before registering this callback."""
    g.whole_callbacks += 1
    _sample_callback(data)
    if _merge_ticks(data):
        _write_snapshot(False)


def _sample_callback(data):
    if isinstance(data, dict):
        g.callback_sample = {
            str(code): {"type": type(tick).__name__,
                        "fields": list(map(str, tick.keys()))[:20] if isinstance(tick, dict) else []}
            for code, tick in list(data.items())[:2]
        }


def _normalize_option_code(raw_code, suffix):
    code = str(raw_code or "").strip().upper()
    if code.startswith("SHO.") and len(code) > 4:
        return code[4:] + ".SHO"
    if code.startswith("SZO.") and len(code) > 4:
        return code[4:] + ".SZO"
    if code.endswith((".SHO", ".SZO")):
        return code
    if code.endswith((".SH", ".SZ")):
        body = code.rsplit(".", 1)[0]
        if len(body) == 8 and body.isdigit():
            return body + suffix
    if len(code) == 8 and code.isdigit():
        return code + suffix
    return ""


def _expiry_text(raw_expiry):
    value = str(raw_expiry or "")
    if len(value) == 8 and value.isdigit():
        return value[:4] + "-" + value[4:6] + "-" + value[6:]
    return value


def _spot_reference(spot_code):
    tick = g.latest_ticks.get(spot_code, {})
    for key in ("lastPrice", "bidPrice", "askPrice"):
        value = _first_number(tick.get(key)) if isinstance(tick, dict) else 0.0
        if value > 0:
            return value
    return 0.0


def _tier_label(tier):
    labels = ["ATM", "TIER1", "TIER2", "TIER3", "TIER4", "TIER5"]
    return labels[tier] if tier < len(labels) else "TIER" + str(tier)


def _underlying_pairs(C, pool_name, spot_code, today_text):
    suffix = ".SZO" if spot_code.endswith(".SZ") else ".SHO"
    calls = {}
    puts = {}
    expiries = {}
    for option_type, target in (("CALL", calls), ("PUT", puts)):
        try:
            codes = C.get_option_list(spot_code, today_text, option_type, True) or []
        except Exception as exc:
            print("option-list failed " + spot_code + " " + option_type + ": " + str(exc))
            codes = []
        for raw_code in codes:
            code = _normalize_option_code(raw_code, suffix)
            if not code:
                continue
            try:
                detail = C.get_option_detail_data(code)
            except Exception:
                detail = {}
            if not isinstance(detail, dict):
                continue
            strike = _first_number(detail.get("OptExercisePrice"))
            expiry = str(detail.get("ExpireDate") or "")
            if strike <= 0 or len(expiry) != 8 or not expiry.isdigit() or expiry < today_text:
                continue
            target[(expiry, strike)] = code
            expiries[(expiry, strike)] = expiry

    common = sorted(set(calls.keys()).intersection(set(puts.keys())))
    if not common:
        return []
    nearest_expiry = min(item[0] for item in common)
    strikes = sorted(item[1] for item in common if item[0] == nearest_expiry)
    if not strikes:
        return []
    spot_price = _spot_reference(spot_code)
    if spot_price <= 0:
        return []
    atm_index = min(range(len(strikes)), key=lambda index: abs(strikes[index] - spot_price))
    ref_atm = strikes[atm_index]
    result = []
    for index, strike in enumerate(strikes):
        tier = abs(index - atm_index)
        if tier > g.max_tiers:
            continue
        key = (nearest_expiry, strike)
        result.append(
            {
                "pool_name": pool_name,
                "spot_code": spot_code,
                "strike": strike,
                "call_code": calls[key],
                "put_code": puts[key],
                "expiry": _expiry_text(nearest_expiry),
                "name": pool_name + " " + _tier_label(tier),
                "atm_tier": tier,
                "ref_atm_strike": ref_atm,
                "is_adjusted": False,
            }
        )
    return result


def _replace_option_subscriptions(C, codes):
    old_ids = list(g.option_subscription_ids.values())
    if g.option_market_subscription_id:
        old_ids.append(g.option_market_subscription_id)
    old_ids.extend(g.option_market_fallback_ids)
    for subscription_id in old_ids:
        try:
            C.unsubscribe_quote(subscription_id)
        except Exception as exc:
            g.errors["unsubscribe"] = str(exc)
    g.option_subscription_ids = {}
    g.option_market_subscription_id = 0
    g.option_market_fallback_ids = []
    # Initial callbacks may arrive synchronously during subscribe_whole_quote.
    g.option_codes = set(codes)
    g.option_aliases = {}
    for code in codes:
        body, market = code.rsplit(".", 1)
        for alias in (code, body, market + "." + body, body + "." + market[:2]):
            g.option_aliases[alias] = code
    g.latest_ticks = {c: t for c, t in g.latest_ticks.items()
                      if c in g.spot_codes or c in g.option_codes}
    g.subscription_failed = []
    g.last_subscribe_attempt = 0.0
    try:
        subscription_id = C.subscribe_whole_quote(sorted(codes), callback=_on_option_market_quote)
        if not subscription_id or int(subscription_id) <= 0:
            raise RuntimeError("whole-quote subscription returned " + str(subscription_id))
        g.option_market_subscription_id = int(subscription_id)
        g.errors.pop("whole_quote_subscribe", None)
    except Exception as exc:
        g.errors["whole_quote_subscribe"] = str(exc)
    # Some Full-QMT builds only push option full quotes when the option market
    # is named explicitly. Keep the contract subscription above as primary and
    # filter this market-wide fallback to the selected contracts in _merge_ticks.
    for market in ("SHO", "SZO"):
        try:
            fallback_id = C.subscribe_whole_quote([market], callback=_on_option_market_quote)
            if not fallback_id or int(fallback_id) <= 0:
                raise RuntimeError("whole-quote " + market + " returned " + str(fallback_id))
            g.option_market_fallback_ids.append(int(fallback_id))
        except Exception as exc:
            g.errors["whole_quote_" + market] = str(exc)
    print("option contracts requested=" + str(len(codes))
          + " whole_quote_id=" + str(g.option_market_subscription_id)
          + " market_fallbacks=" + str(g.option_market_fallback_ids))


def _read_option_full_ticks(C, codes):
    """Read full-book snapshots without get_market_data_ex/Pandas.

    The embedded Full-QMT Python used here does not ship Pandas, while
    get_full_tick returns plain dictionaries including bidPrice/askPrice.
    Splitting requests also avoids a build-specific large-list omission.
    """
    received_keys = []
    for start in range(0, len(codes), 16):
        group = codes[start:start + 16]
        try:
            result = C.get_full_tick(group)
            if isinstance(result, dict):
                received_keys.extend(str(key) for key in result.keys())
                _merge_ticks(result)
        except Exception as exc:
            g.errors["option_full_tick"] = str(exc)
            break
    g.full_tick_option_keys = received_keys[:24]
    if "option_full_tick" not in g.errors:
        g.errors.pop("option_cache", None)


def _read_option_final_quotes(C, codes):
    """Read daily final prices without blocking the embedded QMT runtime.

    In this QMT build, historical ``quoter`` reads can block once per option.
    Live buy/sell books therefore come only from full-quote callbacks and
    get_full_tick; after close this supplies final-price estimates instead.
    """
    received_keys = []
    today = time.strftime("%Y%m%d")
    for code in codes:
        try:
            close = C.get_market_data(
                ["close"], [code], start_time="", end_time="", skip_paused=True,
                period="1d", dividend_type="none", count=-1)
            price = _final_price(close)
            record = {"lastPrice": price} if price > 0 else None
            if record is None:
                continue
            record = dict(record)
            record.setdefault("timetag", today)
            if _merge_ticks({code: record}, from_cache=True):
                received_keys.append(code)
        except Exception as exc:
            g.errors["option_final_quote"] = str(exc)
            break
    g.final_quote_keys = received_keys[:24]
    if "option_final_quote" not in g.errors:
        g.errors.pop("option_final_quote", None)


def _poll_quotes(C, force=False):
    now = time.time()
    if not force and now - g.last_fallback_at < 1.0:
        return
    g.last_fallback_at = now
    today = time.strftime("%Y%m%d")
    g.latest_ticks = {c: t for c, t in g.latest_ticks.items()
                      if not _tick_day(t) or _tick_day(t) == today}
    try:
        full_ticks = C.get_full_tick(g.spot_codes)
        g.full_tick_keys = list(map(str, full_ticks.keys()))[:12] if isinstance(full_ticks, dict) else []
        _merge_ticks(full_ticks)
        g.errors.pop("full_tick", None)
    except Exception as exc:
        g.errors["full_tick"] = str(exc)

    _read_option_full_ticks(C, sorted(g.option_codes))

    # Keep a final-price fallback when Full-QMT is not sending whole-quote
    # callbacks after the close.  This intentionally does not fabricate a
    # buy/sell book from that single price.
    if force or now - g.last_local_at >= 30.0:
        g.last_local_at = now
        _read_option_final_quotes(C, sorted(g.option_codes))

    missing = [c for c in sorted(g.option_codes) if not _has_book(g.latest_ticks.get(c, {}))]
    # The subscription route is distinct from full-push data. Keep IDs so old
    # contracts can be unsubscribed when the selected strikes/month change.
    if missing and now - g.last_subscribe_attempt >= 30.0:
        g.last_subscribe_attempt = now
        g.subscription_failed = []
        for code in missing:
            if code in g.option_subscription_ids:
                continue
            try:
                subscription_id = C.subscribe_quote(code, "tick", "none", "dict", _on_option_quote)
                if not subscription_id or int(subscription_id) <= 0:
                    raise RuntimeError("tick subscription returned " + str(subscription_id))
                g.option_subscription_ids[code] = int(subscription_id)
            except Exception as exc:
                g.subscription_failed.append(code)
                g.errors["tick_subscribe"] = code + ": " + str(exc)
        if not g.subscription_failed:
            g.errors.pop("tick_subscribe", None)

    g.subscription_failed = [c for c in g.subscription_failed
                             if not _has_book(g.latest_ticks.get(c, {}))]
    if force or now - g.last_report_at >= 30.0:
        g.last_report_at = now
        received = sum(1 for c in g.option_codes if c in g.latest_ticks)
        books = sum(1 for c in g.option_codes if _has_book(g.latest_ticks.get(c, {})))
        print("bridge " + g.version + " option quotes=" + str(received)
              + "/" + str(len(g.option_codes)) + " bid_ask=" + str(books)
              + " callbacks=" + str(g.whole_callbacks) + "/" + str(g.tick_callbacks)
              + " errors=" + str(g.errors))
    _write_snapshot(force)


def _refresh_option_chain(C, force=False):
    now = time.time()
    if not force and now - g.last_chain_refresh_at < g.chain_refresh_sec and g.pairs:
        return
    try:
        spot_ticks = C.get_full_tick(g.spot_codes)
        _merge_ticks(spot_ticks)
    except Exception:
        pass
    today_text = time.strftime("%Y%m%d")
    pairs = []
    for pool_name, spot_code in g.spot_items:
        pairs.extend(_underlying_pairs(C, pool_name, spot_code, today_text))
    g.last_chain_refresh_at = now
    if not pairs:
        print("option chain waiting for spot quote")
        _write_snapshot(True)
        return
    required_codes = set()
    for pair in pairs:
        required_codes.add(pair["call_code"])
        required_codes.add(pair["put_code"])
    g.pairs = pairs
    if required_codes != g.option_codes:
        _replace_option_subscriptions(C, required_codes)
    _poll_quotes(C, True)


def init(C):
    g.spot_subscription_id = C.subscribe_whole_quote(g.spot_codes, callback=_on_spot_quote)
    print("full bridge " + g.version + " ready; output=" + g.output_file)


def after_init(C):
    try:
        _merge_ticks(C.get_full_tick(g.spot_codes))
    except Exception as exc:
        print("initial spot quote failed: " + str(exc))
    _refresh_option_chain(C, True)
    _write_snapshot(True)


def handlebar(C):
    if hasattr(C, "is_last_bar") and not C.is_last_bar():
        return
    _refresh_option_chain(C, False)
    _poll_quotes(C)
