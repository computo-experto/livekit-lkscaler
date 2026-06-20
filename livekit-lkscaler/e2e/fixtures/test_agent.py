"""Lightweight long-running agent simulator for e2e scaling tests."""

from __future__ import annotations

import logging
import os
import signal
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_running = True


def _stop(*_args: object) -> None:
    global _running
    _running = False


signal.signal(signal.SIGTERM, _stop)
signal.signal(signal.SIGINT, _stop)


def main() -> None:
    pod_id = os.getenv("LKSCALER_POD_ID", "unknown-pod")
    namespace = os.getenv("LKSCALER_NAMESPACE", "unknown-namespace")
    logger.info("starting lightweight agent simulator pod=%s namespace=%s", pod_id, namespace)

    heartbeat = 0
    while _running:
        logger.info("agent simulator heartbeat=%s pod=%s", heartbeat, pod_id)
        heartbeat += 1
        time.sleep(5)

    logger.info("agent simulator stopping pod=%s", pod_id)


if __name__ == "__main__":
    main()
