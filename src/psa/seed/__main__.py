"""Export or load a deterministic world using caller-supplied seed and time."""

import argparse
from datetime import datetime
from pathlib import Path

from psa.seed import generate_world
from psa.seed.loader import load_world
from psa.store import make_engine, make_session_factory


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("export", "load"):
        child = sub.add_parser(name)
        child.add_argument("--seed", type=int, required=True)
        child.add_argument("--now", type=datetime.fromisoformat, required=True)
        if name == "export":
            child.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    world = generate_world(args.seed, args.now)
    if args.command == "export":
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(world.model_dump_json(indent=2) + "\n", encoding="utf-8")
        print(
            f"Exported {len(world.customers)} customers, {len(world.orders)} orders to {args.out}"
        )
    else:
        engine = make_engine()
        try:
            with make_session_factory(engine).begin() as session:
                load_world(world, session)
            print(f"Loaded {len(world.customers)} customers and {len(world.orders)} orders")
        finally:
            engine.dispose()


if __name__ == "__main__":
    main()
