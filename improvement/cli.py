"""Self-improvement loop from the command line.

    uv run python -m improvement.cli analyze                 # failures -> clusters only (no model calls)
    uv run python -m improvement.cli start [--max-clusters 3] # full loop; stops at the approval interrupt
    uv run python -m improvement.cli resume <thread>          # continue after an error (e.g. daily quota)
    uv run python -m improvement.cli approve <thread> --by <name> [--note ...]
    uv run python -m improvement.cli decline <thread> --by <name> [--note ...]
    uv run python -m improvement.cli status                   # versions, experiments, promotions
"""

import argparse
import json

from sqlalchemy import select

from config.settings import get_settings


def analyze() -> None:
    from db.session import session_scope
    from improvement import registry
    from improvement.clustering.cluster import cluster
    from improvement.collection import collect

    with session_scope() as s:
        base = registry.active(s)
        fs = collect(s, base.version)
        print(f"{base.version}: {len(fs.records)} failures, {fs.renders} renders, {fs.sessions} sessions\n")
        print(f"{'impact':>6}  {'rate':>5}  {'n':>3}  severity  cluster")
        for c in cluster(fs):
            print(f"{c.impact:6.2f}  {c.rate:5.0%}  {len(c.records):3d}  {c.severity:8s}  {c.label[:90]}")


def status() -> None:
    from db.models import AgentVersion, Experiment, Promotion
    from db.session import session_scope
    from improvement import registry

    with session_scope() as s:
        registry.ensure_seed(s)
        print("agent versions:")
        for v in s.scalars(select(AgentVersion).order_by(AgentVersion.created_at)):
            print(f"  {v.status:9s} {v.version}  ({v.origin}) {(v.rationale or '')[:80]}")
        print("experiments:")
        for e in s.scalars(select(Experiment).order_by(Experiment.created_at)):
            print(f"  {str(e.id)[:8]} {e.status:17s} {e.candidate_version}  thread={e.thread_id}  "
                  f"{e.report_path or ''}")
        print("promotions:")
        for p in s.scalars(select(Promotion).order_by(Promotion.created_at)):
            print(f"  {p.created_at:%Y-%m-%d %H:%M} {p.from_version} -> {p.to_version} by {p.approved_by}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("analyze")
    sub.add_parser("status")
    st = sub.add_parser("start")
    st.add_argument("--max-clusters", type=int, default=3)
    r = sub.add_parser("resume")
    r.add_argument("thread")
    for name in ("approve", "decline"):
        d = sub.add_parser(name)
        d.add_argument("thread")
        d.add_argument("--by", required=True)
        d.add_argument("--note", default="")
    a = ap.parse_args()
    get_settings()
    import os

    os.environ["AUTO_EVALUATE"] = "false"  # benchmark runs evaluate inline
    get_settings.cache_clear()
    from improvement import graph as ig

    if a.cmd == "analyze":
        analyze()
    elif a.cmd == "status":
        status()
    elif a.cmd == "start":
        print(json.dumps(ig.start(a.max_clusters), indent=2, default=str))
    elif a.cmd == "resume":
        print(json.dumps(ig.resume(a.thread), indent=2, default=str))
    else:
        print(json.dumps(ig.decide(a.thread, "approve" if a.cmd == "approve" else "decline", a.by, a.note),
                         indent=2, default=str))


if __name__ == "__main__":
    main()
