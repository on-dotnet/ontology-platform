"""Background worker entry point: python -m ontology_platform.worker."""

import asyncio
import logging
import signal
import socket
from pathlib import Path
from uuid import uuid4

from ontology_platform import models  # noqa: F401  (registers all module tables)
from ontology_platform.db import create_database_engine, create_session_factory
from ontology_platform.modules.ai.extraction import ExtractionModels
from ontology_platform.modules.ai.gateway import OpenAIGateway
from ontology_platform.modules.ai.pipeline import make_extractor, make_transcriber
from ontology_platform.modules.documents.processing import (
    register_extractor,
    register_handlers,
    register_vision_transcriber,
)
from ontology_platform.modules.documents.storage import LocalDocumentStorage
from ontology_platform.modules.jobs.runner import run_worker
from ontology_platform.settings import Settings


async def run() -> None:
    settings = Settings()
    engine = create_database_engine(settings.database_url)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    try:
        loop.add_signal_handler(signal.SIGTERM, stop.set)
        session_factory = create_session_factory(engine)
        gateway = OpenAIGateway(settings, session_factory)
        extraction_models = ExtractionModels(
            standard=settings.ai_model, reasoning=settings.ai_reasoning_model
        )
        register_extractor(make_extractor(session_factory, gateway, extraction_models))
        register_vision_transcriber(make_transcriber(gateway, settings.ai_model))
        register_handlers(LocalDocumentStorage(Path(settings.documents_dir)))
        await run_worker(session_factory, f"{socket.gethostname()}-{uuid4()}", stop_event=stop)
    finally:
        loop.remove_signal_handler(signal.SIGTERM)
        await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())
