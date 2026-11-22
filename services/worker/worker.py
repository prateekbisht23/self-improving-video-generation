"""Start a worker:  uv run python -m services.worker.worker

Uses RQ's SimpleWorker (runs jobs in-process). The default Worker forks a child per job,
and on macOS forking after Objective-C / gRPC / CTranslate2 have initialised can crash
("objc ... may have been in progress in another thread when fork() was called").
SimpleWorker avoids fork entirely; the trade-off is no per-job memory isolation.
"""

import logging

from rq import SimpleWorker

from config.settings import get_settings
from services.worker.jobs import get_queue, redis_conn


def main() -> None:
    get_settings()  # export .env (API keys, LANGSMITH_*) before any model call
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    SimpleWorker([get_queue()], connection=redis_conn(), name=None).work(with_scheduler=True)


if __name__ == "__main__":
    main()
