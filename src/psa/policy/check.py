"""CLI: validate policy files and print a rule summary.

uv run python -m psa.policy.check [policies/]
"""

from __future__ import annotations

import sys
from pathlib import Path

from psa.domain import ActionName
from psa.policy.loader import PolicyLoadError, PolicyRegistry


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    root = Path(args[0]) if args else Path("policies")
    try:
        registry = PolicyRegistry.from_dir(root)
    except PolicyLoadError as exc:
        print(f"Policy validation FAILED ({len(exc.issues)} issue(s)):", file=sys.stderr)
        for issue in exc.issues:
            print(f"  - {issue}", file=sys.stderr)
        return 1

    for policy in registry.all():
        print(f"\n{policy.policy_set}@{policy.version}  ({len(policy.rules)} rules)")
        for action in ActionName:
            rule_ids = ", ".join(rule.id for rule in policy.rules_for(action))
            print(f"  {action.value:<20} {rule_ids}")
    print("\nOK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
