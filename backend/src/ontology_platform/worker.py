"""Background worker entry point: python -m ontology_platform.worker."""

import asyncio
import logging
import signal
import socket
from pathlib import Path
from uuid import uuid4

from ontology_platform import models  # noqa: F401  (registers all module tables)
from ontology_platform.db import create_database_engine, create_session_factory
from ontology_platform.modules.ai import assistant, binding_suggest, qa, qa_gap, review_assist
from ontology_platform.modules.ai.extraction import ExtractionModels
from ontology_platform.modules.ai.gateway import OpenAIGateway
from ontology_platform.modules.ai.pipeline import make_extractor, make_transcriber
from ontology_platform.modules.connectors.jobs import register_handlers as register_connector_jobs
from ontology_platform.modules.connectors.service import register_usage_provider
from ontology_platform.modules.cq.service import record_result
from ontology_platform.modules.documents.processing import (
    register_extractor,
    register_handlers,
    register_vision_transcriber,
)
from ontology_platform.modules.documents.storage import LocalDocumentStorage
from ontology_platform.modules.jobs.runner import register, run_worker
from ontology_platform.modules.ontology import bindings as ontology_bindings
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
        extraction_models = ExtractionModels.of(settings)
        register_extractor(
            make_extractor(
                session_factory,
                gateway,
                extraction_models,
                memory_prompt_max=settings.review_memory_prompt_max,
            )
        )
        register_vision_transcriber(make_transcriber(gateway, settings.ai_model))
        register_handlers(LocalDocumentStorage(Path(settings.documents_dir)))
        register(
            assistant.JOB_KIND,
            assistant.make_assistant(session_factory, gateway, settings.ai_model),
        )
        register(
            binding_suggest.JOB_KIND,
            binding_suggest.make_handler(session_factory, gateway, settings.ai_model),
        )
        qa.register_listener(record_result)
        register(qa.JOB_KIND, qa.make_answerer(session_factory, gateway, settings.ai_model))
        register(
            review_assist.JOB_KIND,
            review_assist.make_review_assistant(
                session_factory, gateway, settings.ai_model, settings
            ),
        )
        register(
            qa_gap.JOB_KIND, qa_gap.make_gap_proposer(session_factory, gateway, settings.ai_model)
        )
        register_connector_jobs(session_factory, settings)
        register_usage_provider(ontology_bindings.table_usage)
        await run_worker(
            session_factory,
            f"{socket.gethostname()}-{uuid4()}",
            stop_event=stop,
            concurrency=settings.worker_concurrency,
        )
    finally:
        loop.remove_signal_handler(signal.SIGTERM)
        await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())
