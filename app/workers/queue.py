import logging
from redis import Redis
from rq import Queue

from app.core.config import settings

logger = logging.getLogger(__name__)


def enqueue_message_send(message_id: str, clinic_id: str) -> bool:
    """
    Enfileira o trabalho de envio de mensagem na fila do Redis.
    Se o Redis estiver inacessível (ex: ambiente de teste sem Redis rodando),
    registra o log para processamento ou fallback inline.
    """
    try:
        redis_conn = Redis.from_url(settings.REDIS_URL, socket_connect_timeout=0.1, socket_timeout=0.1)
        queue = Queue("default", connection=redis_conn)
        from app.workers.tasks import run_send_message_job
        job = queue.enqueue(
            run_send_message_job,
            message_id=message_id,
            clinic_id=clinic_id,
            job_timeout=60,
            result_ttl=3600
        )
        logger.info("Mensagem %s enfileirada no Redis (job: %s)", message_id, job.id)
        return True
    except Exception as exc:
        logger.warning(
            "Redis indisponível (%s). O job de mensagem %s não pôde ser enfileirado na fila assíncrona.",
            exc, message_id
        )
        return False
