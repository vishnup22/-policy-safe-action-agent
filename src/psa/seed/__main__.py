"""Export a deterministic world: python -m psa.seed export --seed ... --now ... --out ..."""

import argparse
from datetime import datetime
from pathlib import Path

from psa.seed import generate_world


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export")
    export.add_argument("--seed", type=int, required=True)
    export.add_argument("--now", type=datetime.fromisoformat, required=True)
    export.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    world = generate_world(args.seed, args.now)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(world.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"Exported {len(world.customers)} customers, {len(world.orders)} orders to {args.out}")


if __name__ == "__main__":
    main()
