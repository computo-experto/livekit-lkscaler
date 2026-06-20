"""Test agent for E2E bin-packing verification.

This agent:
- Starts a minimal LiveKit worker process for E2E stack presence checks.
"""

import logging
import os

from livekit.agents import JobContext, WorkerOptions, cli

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def entrypoint(ctx: JobContext) -> None:
    """Minimal worker entrypoint for E2E container liveness."""
    logger.info("Worker accepted job for room %s", ctx.room.name)
    await ctx.connect()


def load_fnc() -> float:
    """Simple load function for deterministic worker availability."""
    return 0.0


if __name__ == "__main__":
    api_key = os.getenv("LIVEKIT_API_KEY", "devkey")
    api_secret = os.getenv("LIVEKIT_API_SECRET", "secret")
    ws_url = os.getenv("LIVEKIT_URL", "ws://livekit:7880")

    logger.info("Starting test worker at %s", ws_url)

    worker_options = WorkerOptions(
        entrypoint_fnc=entrypoint,
        load_fnc=load_fnc,
        ws_url=ws_url,
        api_key=api_key,
        api_secret=api_secret,
    )
    cli.run_app(worker_options)
