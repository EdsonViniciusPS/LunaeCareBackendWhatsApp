import asyncio
import logging
import signal
from redis import Redis
from rq import Worker, Queue

from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [Worker] %(message)s"
)
logger = logging.getLogger("whatsapp-worker")


def run_rq_worker():
    logger.info("Conectando worker ao Redis em: %s", settings.REDIS_URL)
    try:
        redis_conn = Redis.from_url(settings.REDIS_URL)
        queues = ["high", "default", "low", "automations"]
        worker = Worker(
            [Queue(name, connection=redis_conn) for name in queues],
            connection=redis_conn
        )
        logger.info("Worker pronto para processar filas: %s", ", ".join(queues))
        worker.work(with_scheduler=True)
    except Exception as exc:
        logger.error("Erro no worker: %s. Aguardando reconexão...", exc)


if __name__ == "__main__":
    run_rq_worker()
