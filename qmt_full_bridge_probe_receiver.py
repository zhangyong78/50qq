"""Monitor the JSON file written by the read-only Full-QMT probe."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any


QUOTE_FILE = Path(r"D:\mycode\50qq\qmt_full_bridge_probe.json")
TIMEOUT_SECONDS = 90


def first_level(values: Any) -> float | None:
    if not isinstance(values, (list, tuple)) or not values:
        return None
    try:
        return float(values[0])
    except (TypeError, ValueError):
        return None


def main() -> int:
    deadline = time.monotonic() + TIMEOUT_SECONDS
    last_mtime = 0.0

    print(f"WAITING {QUOTE_FILE}", flush=True)
    while time.monotonic() < deadline:
        try:
            mtime = QUOTE_FILE.stat().st_mtime
            if mtime != last_mtime:
                message = json.loads(QUOTE_FILE.read_text(encoding="utf-8"))
                last_mtime = mtime
                ticks = message.get("ticks", {})
                if isinstance(ticks, dict):
                    for code, tick in ticks.items():
                        if not isinstance(tick, dict):
                            continue
                        bid = first_level(tick.get("bidPrice"))
                        ask = first_level(tick.get("askPrice"))
                        print(
                            f"TICK {code} last={tick.get('lastPrice')} bid1={bid} ask1={ask}",
                            flush=True,
                        )
                    has_spot = "510050.SH" in ticks
                    has_option = any(
                        code.endswith((".SHO", ".SZO"))
                        and isinstance(tick, dict)
                        and first_level(tick.get("bidPrice")) is not None
                        and first_level(tick.get("askPrice")) is not None
                        for code, tick in ticks.items()
                    )
                    if has_spot and has_option:
                        print("PASS full-qmt file bridge returned spot and option quotes", flush=True)
                        return 0
        except FileNotFoundError:
            pass
        except (OSError, json.JSONDecodeError) as exc:
            print(f"WAIT {exc}", flush=True)
        time.sleep(0.5)

    print("FAIL timed out waiting for a spot and option quote", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
