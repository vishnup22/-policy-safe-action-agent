"""Follow-up worker: `uv run python -m psa.scheduler [--once] [--interval 5]`."""

import argparse
import time

from psa.clock import SystemClock
from psa.scheduler import Scheduler
from psa.store import make_engine, make_session_factory


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="fire what is due, then exit")
    parser.add_argument("--interval", type=float, default=5.0, help="seconds between polls")
    args = parser.parse_args()
    scheduler = Scheduler(make_session_factory(make_engine()), SystemClock())
    while True:
        for item in scheduler.run_due():
            print(f"fired {item.follow_up_id} conversation={item.conversation_id}", flush=True)
        if args.once:
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
