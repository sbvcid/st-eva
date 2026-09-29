"""Run the evaluation from the command line.

    python -m harness --build --live          # build the snapshot once
    python -m harness --target reference      # grade the reference target
    python -m harness --target scripted --broken wrong-value

A target is a provider adapter. None is bundled for a real vendor, because
shipping one would make the harness depend on a vendor SDK, and the point of it
is to run the same dataset against any model.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

if __package__ in (None, ""):  # pragma: no cover - direct execution
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from harness import dataset as dataset_module
    from harness import reference, report as report_module
    from harness import snapshot as snapshot_module
    from harness.runner import Runner
else:
    from . import dataset as dataset_module
    from . import reference, report as report_module
    from . import snapshot as snapshot_module
    from .runner import Runner


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="ST-EVA 003 eval harness")
    parser.add_argument(
        "--build", action="store_true",
        help="build the evaluation snapshot if it does not exist",
    )
    parser.add_argument(
        "--live", action="store_true",
        help="build the snapshot with SEC ingestion (spends request budget)",
    )
    parser.add_argument(
        "--target", default="reference",
        help="target adapter name; 'scripted' needs --broken",
    )
    parser.add_argument(
        "--broken", default="wrong-value",
        help="which deliberate failure a scripted target should provoke",
    )
    parser.add_argument("--snapshot", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    root = os.path.dirname(os.path.abspath(__file__))
    path = args.snapshot or snapshot_module.default_snapshot_path()

    if args.build:
        built = snapshot_module.build_snapshot(path, live=args.live)
        if built["reused"]:
            print(f"snapshot already present: {path}")
        else:
            print(f"snapshot built: {path}")

    if not os.path.exists(path):
        print(
            f"no snapshot at {path}. Run with --build first.",
            file=sys.stderr,
        )
        return 2

    target = _make_target(args)
    tests = dataset_module.build_dataset(path)
    run = Runner(tests, path, root).run(target)
    report = report_module.build_report(run)
    report_module.write_report(root, report, run.run_dir)

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(report_module.render(report))
    return 0


def _make_target(args):
    if args.target == "scripted":
        broken = reference.broken_targets()
        if args.broken not in broken:
            raise SystemExit(
                f"unknown scripted target {args.broken!r}; "
                f"choose from {sorted(broken)}"
            )
        return broken[args.broken]
    if args.target == "reference":
        return reference.CorrectTarget()
    raise SystemExit(
        f"unknown target {args.target!r}. Implement a Target and register it "
        "in main()."
    )


if __name__ == "__main__":
    raise SystemExit(main())
