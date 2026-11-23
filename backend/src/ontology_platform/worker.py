"""Background worker entry point: `python -m ontology_platform.worker`.

Placeholder until the jobs module provides the real loop (docs/specs/001-m1-ai-ingestion.md §3.3).
"""

import asyncio
import logging

logger = logging.getLogger("ontology_platform.worker")


async def run() -> None:
    logger.info("worker started; no job handlers are registered yet")
    await asyncio.Event().wait()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())
